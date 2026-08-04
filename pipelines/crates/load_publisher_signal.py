#!/usr/bin/env python3
"""
Per-release publishing acts, and withdrawn work.

TWO SIGNALS THE GRAPH HAS NO OTHER SOURCE FOR.

1. WHO ACTUALLY SHIPPED IT. versions.csv carries published_by on 92% of rows
   (33,826 distinct publishers in a 400k sample). Ownership is a permission;
   publishing is an ACT. A crate can be owned by a team of eight while one
   person cuts every release, and the graph currently cannot tell those apart --
   every other edge it holds is "is associated with", never "did this, on this
   date". This is the closest thing to a contribution record in the dump.

2. WHAT THEY TOOK BACK. `yanked` marks a version the author WITHDREW -- broken,
   insecure, or published in error. Every quality signal in the graph so far is
   positive: stars, ratings, downloads, citations. None of them can say "the
   maintainer themselves retracted this". A yank is the author's own negative
   judgement of their work, which no external rater can supply.

WHAT IS WRITTEN, onto person_content edges for domain='crates':

    releases_published   how many versions this person actually cut
    releases_yanked      how many of those were later withdrawn
    yank_rate            yanked/published, only when published >= 5 -- below
                         that the ratio is noise (one yank out of one release
                         reads as 100% and means nothing)
    first_release        earliest publish date by this person
    last_release         latest publish date -- an activity signal grounded in
                         an ACT rather than in repository metadata

DELIBERATELY NOT WRITTEN: yank_rate is never folded into score or rank_score.
Yanking a broken release is RESPONSIBLE behaviour; a maintainer who yanks is
more trustworthy than one who leaves a broken version up. Treating it as a
demerit would invert its meaning, so it is stored as an observation and left for
a consumer to interpret.

Counters use json_extract, never `meta_json LIKE '%key%'`.
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


def counters(g):
    def n(key):
        return g.execute(
            "SELECT COUNT(*) FROM person_content WHERE domain='crates' "
            f"AND json_extract(meta_json,'$.{key}') IS NOT NULL"
        ).fetchone()[0]
    return {"edges_with_releases": n("releases_published"),
            "edges_with_yanked": n("releases_yanked")}


def load(dump_dir, graph_db, apply_changes, limit=0):
    t0 = time.time()
    for f in ("versions.csv", "users.csv", "crates.csv"):
        if not os.path.exists(os.path.join(dump_dir, f)):
            print(f"missing required file: {f}", file=sys.stderr)
            return None

    # crates.io user id -> gh_login. 100% of users carry one (69,169/69,169).
    login_of = {}
    with open(os.path.join(dump_dir, "users.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("id") and row.get("gh_login"):
                login_of[row["id"]] = row["gh_login"].strip()

    crate_name = {}
    with open(os.path.join(dump_dir, "crates.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("id") and row.get("name"):
                crate_name[row["id"]] = row["name"]

    # (login, crate) -> release facts
    pub = defaultdict(int)
    yank = defaultdict(int)
    first = {}
    last = {}
    no_publisher = 0
    with open(os.path.join(dump_dir, "versions.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            uid = (row.get("published_by") or "").strip()
            if not uid:
                no_publisher += 1
                continue
            login = login_of.get(uid)
            # NOTE: load_crates_maintainers.py wrote the raw crate_id into
            # content_ref rather than the crate name, so edges look like
            # ('gh:reem', '13'). Keying on the id is what actually joins today.
            # The name is carried into meta_json below so the edge stops being
            # an opaque integer; content_ref itself is left alone because
            # rewriting a key column is a migration, not a signal load.
            cid = (row.get("crate_id") or "").strip()
            if not login or not cid:
                continue
            k = (login.lower(), cid)
            pub[k] += 1
            if (row.get("yanked") or "").strip() in ("t", "true", "1"):
                yank[k] += 1
            d = (row.get("created_at") or "")[:10]
            if d:
                if k not in first or d < first[k]:
                    first[k] = d
                if k not in last or d > last[k]:
                    last[k] = d

    g = sqlite3.connect(graph_db)
    g.execute("PRAGMA busy_timeout=600000")
    before = counters(g)

    # crates edges are keyed by person_id 'gh:<login>' and content_ref=crate name.
    edges = {}
    for pid, ref, meta in g.execute(
        "SELECT person_id, content_ref, meta_json FROM person_content "
        "WHERE domain='crates'"
    ):
        if pid.startswith("gh:") and ref:
            edges[(pid.split(":", 1)[1].lower(), ref)] = (pid, ref, meta)

    stats = {
        "versions_without_publisher": no_publisher,
        "publisher_crate_pairs": len(pub),
        "edges_matched": 0,
        "total_releases_attributed": 0,
        "total_yanks_attributed": 0,
    }

    updates = []
    for k, n in pub.items():
        row = edges.get(k)
        if not row:
            continue
        stats["edges_matched"] += 1
        if limit and stats["edges_matched"] > limit:
            break
        pid, ref, meta = row
        try:
            m = json.loads(meta) if meta else {}
        except Exception:
            m = {}
        y = yank.get(k, 0)
        # content_ref is a bare crate id; carry the readable name so a consumer
        # does not have to hold the dump to know what edge '13' refers to.
        if crate_name.get(k[1]):
            m["crate_name"] = crate_name[k[1]]
        m["releases_published"] = n
        m["releases_yanked"] = y
        if n >= 5:
            m["yank_rate"] = round(y / n, 4)
        if k in first:
            m["first_release"] = first[k]
        if k in last:
            m["last_release"] = last[k]
        stats["total_releases_attributed"] += n
        stats["total_yanks_attributed"] += y
        updates.append((json.dumps(m), pid, ref))

    stats["edges_updated"] = len(updates)
    stats["before"] = before
    if apply_changes and updates:
        g.executemany(
            "UPDATE person_content SET meta_json=? "
            "WHERE person_id=? AND content_ref=? AND domain='crates'",
            updates,
        )
        g.commit()
        stats["after"] = counters(g)
    stats["applied"] = bool(apply_changes)
    stats["elapsed_s"] = round(time.time() - t0, 2)
    return stats


def main():
    ap = argparse.ArgumentParser(
        description="Per-release publishing acts and yanks onto crates edges.")
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
