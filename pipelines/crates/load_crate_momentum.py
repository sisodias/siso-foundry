#!/usr/bin/env python3
"""
Crate download MOMENTUM from the real time series, not a snapshot.

WHY THIS EXISTS.

Round 4 loaded star velocity from momentum.sqlite and labelled it honestly:
three consecutive days in July 2026, "a momentary reading, not a trend -- a repo
that launched on 2026-07-10 shows enormous velocity while a steady long-term
grower shows little."

crates.io ships version_downloads.csv: one row per (version, day, count) across
roughly 90 days. Rolled up to the crate and split into halves, that is an actual
trend -- recent-half downloads against earlier-half downloads on the same crate,
so a launch spike and a steady grower are distinguishable.

WHAT IS WRITTEN, onto domain='github' edges matched by repository URL (the same
artifact join load_crate_repo_signal.py established, which matched 7,348 edges):

    dl_recent_30d      downloads in the most recent third of the window
    dl_window_days     how many days the series actually spans -- recorded so a
                       consumer can see how narrow the reading is, the same
                       honesty Round 4's momentum_day was written for
    dl_trend           recent-half / earlier-half. >1 rising, <1 fading.
                       Omitted entirely when the earlier half is zero, because
                       a crate that did not exist yet has no trend and writing
                       infinity would be a lie dressed as a number.

NOT written: score is never touched, and this is never folded into
person.rank_score. A download trend is a measurement of the ARTIFACT, not a
judgement of the person, and Round 4 already established that momentum stays out
of the person-level ranking.

Counters use json_extract, never `meta_json LIKE '%key%'` -- LIKE matches values
as well as keys and once reported a baseline of 35 where the truth was 0.
"""

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
import time
from collections import defaultdict

csv.field_size_limit(10 ** 9)

GITHUB_URL = re.compile(r"github\.com[/:]([^/\s]+)/([^/\s#?]+)", re.I)


def repo_from_url(url):
    if not url:
        return None
    m = GITHUB_URL.search(url)
    if not m:
        return None
    repo = m.group(2).removesuffix(".git")
    if not m.group(1) or not repo:
        return None
    return f"{m.group(1)}/{repo}".lower()


def counters(g):
    def n(key):
        return g.execute(
            "SELECT COUNT(*) FROM person_content WHERE domain='github' "
            f"AND json_extract(meta_json,'$.{key}') IS NOT NULL"
        ).fetchone()[0]
    return {"edges_with_dl_recent": n("dl_recent_30d"),
            "edges_with_dl_trend": n("dl_trend")}


def load(dump_dir, graph_db, apply_changes, limit=0):
    t0 = time.time()
    for f in ("versions.csv", "crates.csv", "version_downloads.csv"):
        if not os.path.exists(os.path.join(dump_dir, f)):
            print(f"missing required file: {f}", file=sys.stderr)
            return None

    # version_id -> crate_id
    v2c = {}
    with open(os.path.join(dump_dir, "versions.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("id") and row.get("crate_id"):
                v2c[row["id"]] = row["crate_id"]

    # Pass 1: learn the real date window rather than assuming 90 days.
    days = set()
    with open(os.path.join(dump_dir, "version_downloads.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = row.get("date")
            if d:
                days.add(d)
    if not days:
        print("version_downloads.csv carried no dates", file=sys.stderr)
        return None
    ordered = sorted(days)
    span = len(ordered)
    mid = ordered[span // 2]
    recent_cut = ordered[max(0, span - (span // 3))]

    # Pass 2: roll daily rows up to the crate, split by the learned midpoint.
    early = defaultdict(int)
    late = defaultdict(int)
    recent = defaultdict(int)
    with open(os.path.join(dump_dir, "version_downloads.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = v2c.get(row.get("version_id") or "")
            if not cid:
                continue
            n = (row.get("downloads") or "").strip()
            if not n.isdigit():
                continue
            n = int(n)
            d = row.get("date") or ""
            if d >= mid:
                late[cid] += n
            else:
                early[cid] += n
            if d >= recent_cut:
                recent[cid] += n

    # crate -> github repo (most-downloaded crate wins a shared repo, matching
    # load_crate_repo_signal.py so the two loaders never disagree on a repo).
    best = {}
    with open(os.path.join(dump_dir, "crates.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            repo = repo_from_url(row.get("repository"))
            if not repo:
                continue
            cid = row.get("id")
            tot = late.get(cid, 0) + early.get(cid, 0)
            cur = best.get(repo)
            if cur is None or tot > cur[0]:
                best[repo] = (tot, cid)

    g = sqlite3.connect(graph_db)
    g.execute("PRAGMA busy_timeout=600000")
    before = counters(g)

    edges = defaultdict(list)
    for pid, ref, meta in g.execute(
        "SELECT person_id, content_ref, meta_json FROM person_content "
        "WHERE domain='github'"
    ):
        if ref:
            edges[ref.lower()].append((pid, ref, meta))

    stats = {
        "series_days": span,
        "window_start": ordered[0],
        "window_end": ordered[-1],
        "crates_with_series": len(late) + len(early),
        "repos_matched": 0,
        "edges_updated": 0,
        "trend_omitted_no_baseline": 0,
    }

    updates = []
    for repo, (_, cid) in best.items():
        rows = edges.get(repo)
        if not rows:
            continue
        stats["repos_matched"] += 1
        if limit and stats["repos_matched"] > limit:
            break
        e, l = early.get(cid, 0), late.get(cid, 0)
        for pid, ref, meta in rows:
            try:
                m = json.loads(meta) if meta else {}
            except Exception:
                m = {}
            m["dl_recent_30d"] = recent.get(cid, 0)
            m["dl_window_days"] = span
            if e > 0:
                m["dl_trend"] = round(l / e, 3)
            else:
                stats["trend_omitted_no_baseline"] += 1
            updates.append((json.dumps(m), pid, ref))

    stats["edges_updated"] = len(updates)
    stats["before"] = before
    if apply_changes and updates:
        g.executemany(
            "UPDATE person_content SET meta_json=? "
            "WHERE person_id=? AND content_ref=? AND domain='github'",
            updates,
        )
        g.commit()
        stats["after"] = counters(g)
    stats["applied"] = bool(apply_changes)
    stats["elapsed_s"] = round(time.time() - t0, 2)
    return stats


def main():
    ap = argparse.ArgumentParser(
        description="Crate download momentum from the daily time series.")
    ap.add_argument("--dump", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    s = load(a.dump, a.graph, a.apply, a.limit)
    if s is None:
        return 1
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
