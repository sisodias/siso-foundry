#!/usr/bin/env python3
"""Load real-world adoption signal into the people graph.

WHY THIS EXISTS
---------------
Stars are a vote. Ratings are an opinion. Package downloads and dependent-repo
counts are neither -- they are a measurement of how much other software actually
*depends on* the work. That makes this the strongest quality signal in the
corpus, and it has never reached the graph.

    sqlite> select full_name, downloads, dependent_repos, fame_gap
            from bank_adoption_v2 order by downloads desc limit 3;
    npm/node-semver          |3299256555|1325167|30.2
    mathiasbynens/emoji-regex|1753375141|4193583|42.4
    sindresorhus/find-up     |1176149007|1124485|38.9

`fame_gap` is the interesting column: how far adoption outruns fame. A high
fame_gap is exactly the person a star-ranked graph cannot find -- widely
depended upon, barely starred.

SMALL TABLE, HIGH VALUE. Only 1,026 rows, so this enriches ~1k edges rather
than hundreds of thousands. That is fine: it is the difference between "this
looks popular" and "four million repos break without this". Coverage is
deliberately narrow because resolving a repo to a registry package is hard --
`resolved` and `link_method` record how each one was established.

WHAT THIS WRITES into person_content.meta_json:
  downloads / downloads_period, dependent_repos, dependent_pkgs,
  registry, pkg_name, adoption_score, reach_percentile, fame_gap,
  real_value, adoption_verdict

VERDICT is the rating pass's own conclusion about whether the repo's rated value
survived contact with adoption data: promote (152) / confirm (467) /
demote (95) / unresolved (312). It is stored under `adoption_verdict` rather
than `verdict` so it can never be confused with the `value` written by
load_repo_value.py -- they are different claims from different passes.

Rows with verdict='unresolved' are still loaded when they carry download data,
because the download number is a fact even where the value judgement was not
settled. Rows with neither are skipped.

This loader NEVER creates people. Unmatched owners are counted and skipped.

Usage:
  load_adoption_signal.py --identity identity.sqlite --graph people_v2.sqlite [--apply]
"""
import argparse
import json
import sqlite3
import sys
import time

# meta_json key -> source column. Only written when the source is non-NULL, so
# a sparse row stays sparse rather than filling with nulls.
FIELDS = (
    ("downloads", "downloads"),
    ("downloads_period", "downloads_period"),
    ("dependent_repos", "dependent_repos"),
    ("dependent_pkgs", "dependent_pkgs"),
    ("registry", "registry"),
    ("pkg_name", "pkg_name"),
    ("adoption_score", "adoption_score"),
    ("reach_percentile", "reach_percentile"),
    ("fame_gap", "fame_gap"),
    ("real_value", "real_value"),
    ("adoption_verdict", "verdict"),
)


def load(identity_db, graph_db, apply_changes):
    src = sqlite3.connect(f"file:{identity_db}?mode=ro", uri=True)
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")

    before = {
        "edges_with_downloads": g.execute(
            "SELECT COUNT(*) FROM person_content "
            "WHERE domain='github' AND meta_json LIKE '%downloads%'"
        ).fetchone()[0],
        "edges_with_fame_gap": g.execute(
            "SELECT COUNT(*) FROM person_content "
            "WHERE domain='github' AND meta_json LIKE '%fame_gap%'"
        ).fetchone()[0],
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

    cols = ", ".join(c for _, c in FIELDS)
    rows = src.execute(
        f"SELECT full_name, {cols} FROM bank_adoption_v2 WHERE full_name LIKE '%/%'"
    ).fetchall()

    updates = []
    stats = {
        "source_rows": len(rows), "edges_matched": 0,
        "owner_missing": 0, "no_payload": 0, "with_fame_gap": 0,
    }

    for row in rows:
        full_name = row[0]
        login, _, _ = full_name.partition("/")
        if not login:
            continue
        pid = known.get(login.lower(), f"gh:{login}")
        key = (pid, full_name)
        if key not in existing:
            stats["owner_missing"] += 1
            continue

        payload = {k: v for (k, _), v in zip(FIELDS, row[1:]) if v is not None}
        if not payload:
            stats["no_payload"] += 1
            continue

        try:
            meta = json.loads(existing[key] or "{}")
        except (ValueError, TypeError):
            meta = {}
        meta.update(payload)
        if "fame_gap" in payload:
            stats["with_fame_gap"] += 1
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
            "edges_with_downloads": g.execute(
                "SELECT COUNT(*) FROM person_content "
                "WHERE domain='github' AND meta_json LIKE '%downloads%'"
            ).fetchone()[0],
            "edges_with_fame_gap": g.execute(
                "SELECT COUNT(*) FROM person_content "
                "WHERE domain='github' AND meta_json LIKE '%fame_gap%'"
            ).fetchone()[0],
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
