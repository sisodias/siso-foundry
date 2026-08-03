#!/usr/bin/env python3
"""Load recency, lifecycle and liftability signal into the people graph.

WHY THIS EXISTS
---------------
The graph cannot currently tell a 2011 abandoned repo from last week's work.
Every github edge carries stars, a description and (since load_repo_value.py) a
value rating -- but nothing temporal. So two questions that matter most for
"who should I actually talk to / hire / read" are unanswerable:

  "Who is ACTIVE right now?"  and  "Whose work has been abandoned?"

The data has been on disk the whole time:

    sqlite> select count(*) from repo_card where pushed_at >= '2025';
    494167
    sqlite> select sum(archived=1) from repo_card;
    106994

A third signal rides along in the same pass because it shares the join key and
the target column -- `bank_liftable_ranked.liftability` (32,071 repos), which
answers the Foundry's actual core question: not "is this good" but "can I lift
this into my own system".

WHAT THIS WRITES -- all into person_content.meta_json, no schema change:
  pushed_at    ISO date of last push
  created_at   ISO date of creation
  archived     1 only when true (absent = not archived; keeps meta small)
  liftability  0-100 where rated
  unit_class   what kind of liftable unit it is

WHY META_JSON AND NOT NEW COLUMNS. person_content is keyed
(person_id, domain, content_ref, role) and shared across four domains. A
`pushed_at` column would be NULL for every book row -- a github-shaped column on
a domain-agnostic table. meta_json is already the per-domain extension point and
is what load_repo_value.py used.

OBSERVED_AT. person_content has a real `observed_at` column that is currently
the load timestamp -- i.e. when WE looked, not when the fact was true. That is
the wrong semantics and the schema comment says so ("when it was true"). This
loader sets observed_at to the repo's pushed_at where known, which is the
closest thing to a truth-time this data has.

This loader NEVER creates people. Unmatched owners are counted and skipped.

Usage:
  load_activity_signal.py --identity identity.sqlite --graph people_v2.sqlite [--apply]
"""
import argparse
import json
import sqlite3
import sys
import time


def load(identity_db, graph_db, apply_changes, limit=0):
    src = sqlite3.connect(f"file:{identity_db}?mode=ro", uri=True)
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")

    before = {
        "edges_with_pushed_at": g.execute(
            "SELECT COUNT(*) FROM person_content "
            "WHERE domain='github' AND meta_json LIKE '%pushed_at%'"
        ).fetchone()[0],
        "edges_with_liftability": g.execute(
            "SELECT COUNT(*) FROM person_content "
            "WHERE domain='github' AND meta_json LIKE '%liftability%'"
        ).fetchone()[0],
        "edges_archived": g.execute(
            "SELECT COUNT(*) FROM person_content "
            "WHERE domain='github' AND meta_json LIKE '%\"archived\"%'"
        ).fetchone()[0],
    }

    # Liftability first -- small table, held in memory and joined on full_name.
    lift = {}
    for full_name, liftability, unit_class in src.execute(
        "SELECT full_name, liftability, unit_class FROM bank_liftable_ranked "
        "WHERE liftability IS NOT NULL"
    ):
        lift[full_name] = (liftability, unit_class)

    existing = {}
    for pid, ref, meta in g.execute(
        "SELECT person_id, content_ref, meta_json FROM person_content "
        "WHERE domain='github'"
    ):
        existing[(pid, ref)] = meta

    known = {}
    for pid, value in g.execute(
        "SELECT person_id, value FROM external_ids WHERE platform='github_login'"
    ):
        known[(value or "").lower()] = pid

    q = """
        SELECT full_name, pushed_at, created_at, archived
        FROM repo_card
        WHERE full_name LIKE '%/%'
    """
    if limit:
        q += f" LIMIT {int(limit)}"

    updates = []
    stats = {
        "rows_scanned": 0, "edges_matched": 0, "owner_missing": 0,
        "with_pushed": 0, "with_archived": 0, "with_lift": 0,
    }

    for full_name, pushed_at, created_at, archived in src.execute(q):
        stats["rows_scanned"] += 1
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

        touched = False
        if pushed_at:
            meta["pushed_at"] = pushed_at
            stats["with_pushed"] += 1
            touched = True
        if created_at:
            meta["created_at"] = created_at
            touched = True
        if archived == 1:
            meta["archived"] = 1
            stats["with_archived"] += 1
            touched = True
        if full_name in lift:
            liftability, unit_class = lift[full_name]
            meta["liftability"] = liftability
            if unit_class:
                meta["unit_class"] = unit_class
            stats["with_lift"] += 1
            touched = True

        if not touched:
            continue
        stats["edges_matched"] += 1
        # observed_at = when the fact was true (last push), not when we looked.
        updates.append((json.dumps(meta), pushed_at or None, pid, full_name))

    summary = dict(stats)
    summary["before"] = before
    summary["applied"] = bool(apply_changes)

    if apply_changes:
        g.executemany(
            "UPDATE person_content "
            "SET meta_json=?, observed_at=COALESCE(?, observed_at) "
            "WHERE person_id=? AND domain='github' AND content_ref=?",
            updates,
        )
        g.commit()
        summary["after"] = {
            "edges_with_pushed_at": g.execute(
                "SELECT COUNT(*) FROM person_content "
                "WHERE domain='github' AND meta_json LIKE '%pushed_at%'"
            ).fetchone()[0],
            "edges_with_liftability": g.execute(
                "SELECT COUNT(*) FROM person_content "
                "WHERE domain='github' AND meta_json LIKE '%liftability%'"
            ).fetchone()[0],
            "edges_archived": g.execute(
                "SELECT COUNT(*) FROM person_content "
                "WHERE domain='github' AND meta_json LIKE '%\"archived\"%'"
            ).fetchone()[0],
        }

    g.close()
    src.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--identity", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = load(a.identity, a.graph, a.apply, a.limit)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
