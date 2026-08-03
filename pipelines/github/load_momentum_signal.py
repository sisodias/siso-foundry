#!/usr/bin/env python3
"""Load repo momentum (star velocity) into the people graph.

WHY THIS EXISTS
---------------
After load_activity_signal.py the graph knows WHEN work was last touched. It
still does not know whether that work is RISING or FADING. "Who is gaining
attention right now" is a different question from "who is active" and from "who
is famous", and it is the one that finds people before they are obvious.

momentum.sqlite has carried the answer all along:

    sqlite> select count(distinct full_name), count(*) from repo_snapshot;
    56688|170062
    sqlite> select day, count(*) from repo_snapshot group by 1 order by 1;
    2026-07-09|56687
    2026-07-10|56687
    2026-07-11|56688

Verified unused before writing this, by content rather than by proxy:
`grep -rn momentum --include=*.py` across the repo returns no loader, and every
edge in the graph is sourced github_identity / gutenberg / v1_migration -- no
momentum source exists. The 35 edges whose meta_json matches '%velocity%' are
repos NAMED velocity (julianshapiro/velocity, iampawan/VelocityX), not velocity
data -- which is also why the counters below match on the exact JSON key via
json_extract rather than a LIKE.

WHAT THIS WRITES into person_content.meta_json:
  star_velocity   stars/day, from the most recent snapshot
  momentum_day    the snapshot date the velocity came from
  stars_observed  star count at that snapshot
  star_delta      change across the observed window (last - first), NULL if
                  only one snapshot exists for the repo

HONEST SCOPE -- READ THIS BEFORE TRUSTING THE NUMBER. The window is three
consecutive days in July 2026. That is a momentary reading, not a trend:
a repo that launched on 2026-07-10 shows enormous velocity, and a steady
long-term grower shows little. `momentum_day` is written alongside the value
precisely so a consumer can see how stale and how narrow the reading is, rather
than treating it as a standing property of the person. It is deliberately NOT
folded into person.rank_score for the same reason.

Velocity is taken from the LATEST snapshot per repo rather than averaged: an
average over three days of a mostly-flat series mostly measures the flat days.
star_delta carries the window's actual movement for anyone who wants it.

This loader NEVER creates people. Unmatched owners are counted and skipped.

Usage:
  load_momentum_signal.py --momentum momentum.sqlite --graph people_v2.sqlite [--apply]
"""
import argparse
import json
import sqlite3
import sys
import time


def load(momentum_db, graph_db, apply_changes, min_velocity=None):
    src = sqlite3.connect(f"file:{momentum_db}?mode=ro", uri=True)
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")

    # json_extract, not LIKE: a LIKE '%velocity%' also matches repos NAMED
    # velocity (julianshapiro/velocity), which would inflate this by 35.
    count_sql = (
        "SELECT COUNT(*) FROM person_content WHERE domain='github' "
        "AND json_extract(meta_json,'$.star_velocity') IS NOT NULL"
    )
    before = {"edges_with_velocity": g.execute(count_sql).fetchone()[0]}

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

    # Collapse the series to one row per repo: latest velocity, plus the delta
    # across whatever window exists.
    series = {}
    for day, full_name, stars, velocity in src.execute(
        "SELECT day, full_name, stars, star_velocity FROM repo_snapshot "
        "ORDER BY full_name, day"
    ):
        s = series.setdefault(
            full_name,
            {"first_stars": stars, "last_stars": stars, "day": day,
             "velocity": velocity, "n": 0},
        )
        s["last_stars"] = stars
        s["day"] = day
        s["velocity"] = velocity
        s["n"] += 1

    updates = []
    stats = {
        "repos_in_series": len(series), "edges_matched": 0,
        "owner_missing": 0, "below_threshold": 0,
    }

    for full_name, s in series.items():
        if min_velocity is not None and (s["velocity"] or 0) < min_velocity:
            stats["below_threshold"] += 1
            continue
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
        if s["velocity"] is not None:
            meta["star_velocity"] = s["velocity"]
        meta["momentum_day"] = s["day"]
        if s["last_stars"] is not None:
            meta["stars_observed"] = s["last_stars"]
        if s["n"] > 1 and None not in (s["first_stars"], s["last_stars"]):
            meta["star_delta"] = s["last_stars"] - s["first_stars"]
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
            "edges_with_velocity": g.execute(count_sql).fetchone()[0],
        }

    g.close()
    src.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--momentum", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--min-velocity", type=float, default=None)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = load(a.momentum, a.graph, a.apply, a.min_velocity)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
