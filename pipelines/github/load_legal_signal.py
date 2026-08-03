#!/usr/bin/env python3
"""Load legal lane and reuse-shape signal into the people graph.

WHY THIS EXISTS
---------------
Round 2 put `liftability` on 36,516 edges -- "how technically extractable is
this". That is only half the question anyone lifting code actually has. The
other half is whether they are ALLOWED to, and in what shape. A GPL library and
an MIT library can have identical liftability and completely different answers.

`repo_category` carries the structured verdict, and no loader had read it:

    sqlite> select legal_lane, count(*) from repo_category
            where legal_lane is not null and legal_lane != '' group by 1;
    shippable|5730
    unknown|2682
    blocked|999
    reference_only|77

plus three more columns describing the SHAPE of the value:

    value_type   CODE 4926 | BOTH 3125 | INFO 928 | NEITHER 10
    depend_able  9,488 rated
    compose_note 16,124 written

WHY NOT bank_gold.why. `bank_gold` holds 29,937 human-written rationales whose
text begins with a bracketed license lane, e.g.
"[CODE|0BSD (permissive)] Breadth-first, friendlier drop-in replacement...".
Parsing a lane out of that prose is fragile -- the corpus uses at least four
punctuation variants for the same license ("MIT (permissive, reusable)]",
"MIT - permissive, fully reus", "MIT - permissive, reusable.]"), so a parser
would silently mis-bucket. `repo_category.legal_lane` is the same judgement in a
proper column. Use the column, not the prose.

WHAT THIS WRITES into person_content.meta_json:
  legal_lane    shippable | blocked | reference_only | unknown
  value_type    CODE | INFO | BOTH | NEITHER
  depend_able   whether this is safe to depend on
  compose_note  one line on how it composes

`unknown` IS LOADED DELIBERATELY. "We looked and could not tell" is a different
and more useful state than "we never looked", and only writing the confident
lanes would make those two indistinguishable -- the same honest-null principle
that keeps 238k GitHub owners at kind='unknown' rather than guessed.

MAX() per repo across its category rows, matching load_repo_value.py: these are
per-assignment columns and a repo's lane is its best justified assessment.

This loader NEVER creates people. Unmatched owners are counted and skipped.

Usage:
  load_legal_signal.py --identity identity.sqlite --graph people_v2.sqlite [--apply]
"""
import argparse
import json
import sqlite3
import sys
import time

COUNT_SQL = (
    "SELECT COUNT(*) FROM person_content WHERE domain='github' "
    "AND json_extract(meta_json,'$.legal_lane') IS NOT NULL"
)
SHIPPABLE_SQL = (
    "SELECT COUNT(*) FROM person_content WHERE domain='github' "
    "AND json_extract(meta_json,'$.legal_lane')='shippable'"
)


def load(identity_db, graph_db, apply_changes):
    src = sqlite3.connect(f"file:{identity_db}?mode=ro", uri=True)
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")

    before = {
        "edges_with_lane": g.execute(COUNT_SQL).fetchone()[0],
        "edges_shippable": g.execute(SHIPPABLE_SQL).fetchone()[0],
    }

    known = {}
    for pid, value in g.execute(
        "SELECT person_id, value FROM external_ids WHERE platform='github_login'"
    ):
        known[(value or "").lower()] = pid

    existing = {}
    for pid, ref, meta in g.execute(
        "SELECT person_id, content_ref, meta_json FROM person_content "
        "WHERE domain='github'"
    ):
        existing[(pid, ref)] = meta

    rows = src.execute(
        """
        SELECT full_name,
               MAX(legal_lane), MAX(value_type),
               MAX(depend_able), MAX(compose_note)
        FROM repo_category
        WHERE full_name LIKE '%/%'
          AND (   (legal_lane   IS NOT NULL AND legal_lane   != '')
               OR (value_type   IS NOT NULL AND value_type   != '')
               OR depend_able IS NOT NULL
               OR (compose_note IS NOT NULL AND compose_note != ''))
        GROUP BY full_name
        """
    ).fetchall()

    updates = []
    stats = {
        "source_repos": len(rows), "edges_matched": 0,
        "owner_missing": 0, "with_lane": 0, "shippable": 0, "blocked": 0,
    }

    for full_name, lane, value_type, depend_able, compose_note in rows:
        login, _, _ = full_name.partition("/")
        if not login:
            continue
        pid = known.get(login.lower(), f"gh:{login}")
        key = (pid, full_name)
        if key not in existing:
            stats["owner_missing"] += 1
            continue

        try:
            meta = json.loads(existing[key] or "{}")
        except (ValueError, TypeError):
            meta = {}
        if lane:
            meta["legal_lane"] = lane
            stats["with_lane"] += 1
            if lane == "shippable":
                stats["shippable"] += 1
            elif lane == "blocked":
                stats["blocked"] += 1
        if value_type:
            meta["value_type"] = value_type
        if depend_able is not None:
            meta["depend_able"] = depend_able
        if compose_note:
            meta["compose_note"] = compose_note[:300]
        stats["edges_matched"] += 1
        updates.append((json.dumps(meta), pid, full_name))

    summary = dict(stats)
    summary["before"] = before
    summary["applied"] = bool(apply_changes)

    if apply_changes:
        g.executemany(
            "UPDATE person_content SET meta_json=? "
            "WHERE person_id=? AND domain='github' AND content_ref=?",
            updates,
        )
        g.commit()
        summary["after"] = {
            "edges_with_lane": g.execute(COUNT_SQL).fetchone()[0],
            "edges_shippable": g.execute(SHIPPABLE_SQL).fetchone()[0],
        }

    g.close()
    src.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--identity", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = load(a.identity, a.graph, a.apply)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
