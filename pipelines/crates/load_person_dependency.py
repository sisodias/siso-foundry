#!/usr/bin/env python3
"""
person -> person edges derived from CRATE DEPENDENCIES.

THE THIRD ATTEMPT AT THE HARDEST TABLE IN THE GRAPH, and the first that works.

Every edge the graph holds is person -> artifact. It has no representation of
one person relating to another. Three sources have been tried:

  Round 4  naive co-membership on shared gh_category
           -> 720,107,620 pairs. REJECTED: "both wrote a CLI utility" is not a
              relationship, and 15,799 owners in one category is 124.8M pairs
              from that category alone.
  Round 14 Wikidata doctoral advisors (P184)
           -> 271,423 edges available, FIVE with both endpoints in our graph.
              Wikidata's advisor graph is academics and historical figures; our
              population is living developers. Populations that do not overlap
              cannot be joined by any method.
  HERE     crate dependency edges
           -> 233,540 distinct person pairs from a 2.5M-row sample alone.

WHY THIS ONE IS DIFFERENT. A dependency is not an inferred affinity, it is a
declared technical fact: A's software does not build or run without B's. It was
written by the maintainer, it is machine-checked by the package manager, and it
carries a direction that means something. That is exactly the scarcity gate
Round 4 said was missing ("shared RARE category, co-citation, or genuine
co-contribution, which this data does not have") -- this data does have it.

KIND MATTERS AND IS NOT FLATTENED. dependencies.kind is 0=normal, 1=build,
2=dev. Measured on a 1.5M sample: 1,293,470 normal / 167,765 dev / 38,765 build.
Only kind=0 (runtime) is loaded. A dev-dependency means "I test with your
thing"; a runtime dependency means "my thing breaks without yours". Merging them
would repeat the error of flattening book roles, where a volunteer editor became
the second most prolific author in history.

DIRECTION IS PRESERVED. depends_on is not symmetric: A depending on B says B is
load-bearing for A, and the reverse claim is simply false. Stored as
(person_a=dependent, person_b=depended_upon, relation='depends_on',
direction='a_to_b'), matching the person_person shape.

WEIGHT IS EVIDENCE COUNT, NOT IMPORTANCE. `weight` records how many distinct
crate-version dependency rows back the pair. Byron -> dtolnay at 21,815 means
the relation is heavily attested, NOT that Byron owes dtolnay 21,815 favours.
Recorded as evidence so a consumer can threshold it themselves.

SELF-EDGES ARE DROPPED. A maintainer whose crate depends on their own other
crate is not a person-to-person relation.
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict

csv.field_size_limit(10 ** 9)

SCHEMA = """
CREATE TABLE IF NOT EXISTS person_person (
  person_a    TEXT NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
  person_b    TEXT NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
  relation    TEXT NOT NULL,
  direction   TEXT NOT NULL DEFAULT 'a_to_b',
  weight      INTEGER NOT NULL DEFAULT 1,
  confidence  REAL NOT NULL DEFAULT 0.9,
  source      TEXT NOT NULL,
  observed_at TEXT,
  meta_json   TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (person_a, person_b, relation),
  CHECK (person_a <> person_b)
);
CREATE INDEX IF NOT EXISTS ix_pp_a ON person_person(person_a);
CREATE INDEX IF NOT EXISTS ix_pp_b ON person_person(person_b);
CREATE INDEX IF NOT EXISTS ix_pp_rel ON person_person(relation);
"""


def counters(g):
    try:
        total = g.execute("SELECT COUNT(*) FROM person_person").fetchone()[0]
        dep = g.execute(
            "SELECT COUNT(*) FROM person_person WHERE relation='depends_on'"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        total, dep = 0, 0
    return {"person_person_total": total, "depends_on_edges": dep}


def load(dump_dir, graph_db, apply_changes, min_weight=1, limit=0):
    t0 = time.time()
    for f in ("dependencies.csv", "versions.csv"):
        if not os.path.exists(os.path.join(dump_dir, f)):
            print(f"missing required file: {f}", file=sys.stderr)
            return None

    # version_id -> crate_id. A dependency row says "this VERSION of some crate
    # depends on that CRATE", so the dependent side needs the lookup.
    v2c = {}
    with open(os.path.join(dump_dir, "versions.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("id") and row.get("crate_id"):
                v2c[row["id"]] = row["crate_id"]

    g = sqlite3.connect(graph_db)
    g.execute("PRAGMA busy_timeout=600000")
    g.executescript(SCHEMA)
    before = counters(g)

    # crate (content_ref, which is a bare crate id on these edges) -> owners
    owners = defaultdict(set)
    for pid, ref in g.execute(
        "SELECT person_id, content_ref FROM person_content WHERE domain='crates'"
    ):
        if ref:
            owners[ref].add(pid)

    stats = {
        "dependency_rows": 0,
        "runtime_rows": 0,
        "skipped_non_runtime": 0,
        "pairs_distinct": 0,
        "self_edges_dropped": 0,
        "crates_with_owner": len(owners),
    }

    pairs = defaultdict(int)
    with open(os.path.join(dump_dir, "dependencies.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            stats["dependency_rows"] += 1
            if (row.get("kind") or "0").strip() != "0":
                stats["skipped_non_runtime"] += 1
                continue
            stats["runtime_rows"] += 1
            dep_crate = row.get("crate_id")
            src_crate = v2c.get(row.get("version_id") or "")
            if not dep_crate or not src_crate or dep_crate == src_crate:
                continue
            a_side = owners.get(src_crate)
            b_side = owners.get(dep_crate)
            if not a_side or not b_side:
                continue
            for a in a_side:
                for b in b_side:
                    if a == b:
                        stats["self_edges_dropped"] += 1
                        continue
                    pairs[(a, b)] += 1

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rows = []
    for (a, b), w in pairs.items():
        if w < min_weight:
            continue
        if limit and len(rows) >= limit:
            break
        rows.append((
            a, b, "depends_on", "a_to_b", w, 0.95,
            "crates_io_dependencies", now,
            json.dumps({"dependency_rows": w}),
        ))

    stats["pairs_distinct"] = len(pairs)
    stats["edges_to_write"] = len(rows)
    stats["before"] = before

    if apply_changes and rows:
        g.executemany(
            "INSERT OR IGNORE INTO person_person "
            "(person_a,person_b,relation,direction,weight,confidence,"
            " source,observed_at,meta_json) VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )
        g.commit()
        stats["after"] = counters(g)
    stats["applied"] = bool(apply_changes)
    stats["elapsed_s"] = round(time.time() - t0, 2)
    return stats


def main():
    ap = argparse.ArgumentParser(
        description="person->person depends_on edges from crate dependencies.")
    ap.add_argument("--dump", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--min-weight", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    s = load(a.dump, a.graph, a.apply, a.min_weight, a.limit)
    if s is None:
        return 1
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
