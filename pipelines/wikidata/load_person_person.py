"""Load person-to-person relations from Wikidata into the people graph.

WHY THIS EXISTS
---------------
The graph already holds edges from a person to a UNIT OF OUTPUT (person_content)
and cross-platform identifiers (external_ids). The third axis -- person to
person -- was always going to land, and Wikidata is the right source: doctoral
advisor (P184), student (P802), student_of (P1066) and influenced_by (P737)
are the four relations that carry intellectual lineage, and they exist on
Wikidata for ~500k historical figures.

The schema's header comment on why `role` moved to the edge applies here
verbatim:

    A person is not globally "an author" -- they authored THIS work and
    translated THAT one.

    -> role moves to the edge, where it belongs.

A person is also not globally "Plato's student" -- Aristotle was Plato's
student in a different sense from Aristotle being Alexander's teacher, and
P802 vs P184 vs P737 are not the same relation flattened to undirected.
Direction is part of the claim. We record it as two columns:
`relation` (the P-number as a string) and a `direction` flag that names
who is the source of the relation on Wikidata (subject of the P-statement).

THE TABLE
---------
person_person does not exist yet. It is created here, guarded by IF NOT
EXISTS, in the same style as person_content: composite primary key on the
two endpoints plus the relation, with provenance columns source / observed_at
and a confidence for the relation itself. FKs to person(person_id) cascade on
delete so a removed person removes their edges without orphaning rows.

Both endpoints MUST already resolve to a person_id in the graph. This loader
NEVER creates people -- silent person creation from a single relation claim
is the failure mode the schema's identity_claim design exists to prevent, and
the matcher (not this loader) is the right place to mint a new person from
a Wikidata QID. Edges with an unresolved endpoint are DROPPED and counted
in the summary, so the caller knows how much of the source is unrecoverable
without a downstream matcher pass.

Usage:
  load_person_person.py --wikidata relations.jsonl --graph people_v2.sqlite [--apply]
"""
import argparse
import json
import os
import sqlite3
import sys
import time

# Wikidata property id -> (relation name, direction).
# `direction` names who is the SUBJECT of the Wikidata statement: P184 means
# "X has doctoral advisor Y", so X is the subject. Storing the direction makes
# the edge queryable as "give me everyone who studied under Y" without
# needing a second edge in the opposite direction.
RELATIONS = {
    "P184":  ("doctoral_advisor", "subject_has_advisor"),
    "P802":  ("student",          "subject_has_student"),
    "P1066": ("student_of",       "subject_studied_under"),
    "P737":  ("influenced_by",    "subject_was_influenced_by"),
}


def _ensure_table(g):
    """Create person_person if missing. Mirrors the column-naming style and
    provenance pattern of person_content in core/people_schema_v2.sql."""
    g.execute("""
        CREATE TABLE IF NOT EXISTS person_person (
          person_a    TEXT NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
          person_b    TEXT NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
          relation    TEXT NOT NULL,
          direction   TEXT NOT NULL,
          confidence  REAL NOT NULL DEFAULT 0.95,
          source      TEXT NOT NULL DEFAULT 'wikidata_dump',
          observed_at TEXT,
          meta_json   TEXT NOT NULL DEFAULT '{}',
          PRIMARY KEY (person_a, person_b, relation),
          CHECK (person_a <> person_b)
        )
    """)
    g.execute(
        "CREATE INDEX IF NOT EXISTS ix_pp_a ON person_person(person_a)"
    )
    g.execute(
        "CREATE INDEX IF NOT EXISTS ix_pp_b ON person_person(person_b)"
    )
    g.execute(
        "CREATE INDEX IF NOT EXISTS ix_pp_relation ON person_person(relation)"
    )


def load(wikidata_path, graph_db, apply_changes, limit=0):
    if not os.path.exists(wikidata_path):
        raise SystemExit(f"missing input file: {wikidata_path}")

    # The graph is WAL and another loader may hold a long write batch against
    # it. Waiting is correct here -- this loader is idempotent and not urgent,
    # whereas killing a running API grind throws away rate-limited work.
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")

    # --- before ------------------------------------------------------------
    # Count edges per relation we plan to write. CHECK the TABLE first --
    # the loader creates it on first run, and on subsequent runs the count
    # is well-defined.
    before_relations = {}
    for prop in RELATIONS:
        before_relations[prop] = g.execute(
            "SELECT COUNT(*) FROM person_person WHERE relation=?",
            (prop,),
        ).fetchone()[0]
    before = {
        "person_person_total": g.execute(
            "SELECT COUNT(*) FROM person_person"
        ).fetchone()[0],
        "by_relation": before_relations,
    }

    # Build the join map: every identifier we recognise can resolve to a
    # person_id. Wikidata QID and VIAF are the authority identifiers; the
    # voluntary platforms are kept as a fallback because some records arrive
    # without a QID.
    qid_to_pid = {}
    gh_to_pid = {}
    viaf_to_pid = {}
    for pid, platform, value in g.execute(
        "SELECT person_id, platform, value FROM external_ids"
    ):
        if not value:
            continue
        if platform == "wikidata":
            qid_to_pid[value] = pid
        elif platform == "github_login":
            gh_to_pid[value.lower()] = pid
        elif platform == "viaf":
            viaf_to_pid[value] = pid

    # Pre-load existing edges so we only write missing ones. Pulling the set
    # once beats 500k point lookups against a multi-million-row table.
    existing_edges = set()
    for a, b, rel in g.execute(
        "SELECT person_a, person_b, relation FROM person_person"
    ):
        existing_edges.add((a, b, rel))

    edge_rows = []         # (person_a, person_b, relation, direction, confidence, source, observed_at, meta_json)
    stats = {
        "records_seen": 0,
        "relations_seen": 0,
        "edges_resolved": 0,
        "edges_dropped_missing_endpoint": 0,
        "edges_already_present": 0,
    }

    def _resolve(qid):
        if not qid:
            return None
        return qid_to_pid.get(qid)

    with open(wikidata_path, "r", encoding="utf-8") as f:
        for line in f:
            if limit and stats["edges_resolved"] >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            stats["records_seen"] += 1

            subject_qid = rec.get("qid") or rec.get("subject_qid")
            if not subject_qid:
                continue
            subject_pid = _resolve(subject_qid)
            if subject_pid is None:
                # Whole record unresolved: skip rather than minting a person.
                # The matcher, not this loader, decides whether the QID earns
                # a person_id.
                continue

            for prop, (rel_name, direction) in RELATIONS.items():
                # Same property-shape tolerance as load_wikidata_identities.
                target = rec.get(prop)
                if isinstance(target, dict):
                    target = target.get("qid") or target.get("value")
                if not target:
                    continue
                stats["relations_seen"] += 1
                target_pid = _resolve(target)
                if target_pid is None:
                    stats["edges_dropped_missing_endpoint"] += 1
                    continue

                key = (subject_pid, target_pid, rel_name)
                if key in existing_edges:
                    stats["edges_already_present"] += 1
                    continue

                edge_rows.append((
                    subject_pid, target_pid, rel_name, direction,
                    0.95, "wikidata_dump", None, "{}",
                ))
                stats["edges_resolved"] += 1
                # Also block the reverse: a (B, A, same_relation) edge
                # would assert a different claim (P184 is asymmetric), so
                # we do NOT add it.
                existing_edges.add(key)

    summary = {
        "records_seen": stats["records_seen"],
        "relations_seen": stats["relations_seen"],
        "edges_resolved": stats["edges_resolved"],
        "edges_dropped_missing_endpoint": stats["edges_dropped_missing_endpoint"],
        "edges_already_present": stats["edges_already_present"],
        "before": before,
        "applied": bool(apply_changes),
    }

    if apply_changes:
        # The table may not exist yet on first run; create it before writing.
        _ensure_table(g)
        g.executemany(
            "INSERT OR IGNORE INTO person_person "
            "(person_a,person_b,relation,direction,confidence,source,observed_at,meta_json) "
            "VALUES (?,?,?,?,?,?,?,?)",
            edge_rows,
        )
        g.commit()
        after_relations = {}
        for prop in RELATIONS:
            after_relations[prop] = g.execute(
                "SELECT COUNT(*) FROM person_person WHERE relation=?",
                (prop,),
            ).fetchone()[0]
        summary["after"] = {
            "person_person_total": g.execute(
                "SELECT COUNT(*) FROM person_person"
            ).fetchone()[0],
            "by_relation": after_relations,
        }

    g.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wikidata", required=True,
                    help="path to a JSONL file of Wikidata person-to-person records")
    ap.add_argument("--graph", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = load(a.wikidata, a.graph, a.apply, a.limit)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
