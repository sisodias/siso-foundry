#!/usr/bin/env python3
"""
Admit crates.io publishers the star floor hides, on EVIDENCE OF USE.

THE PROBLEM.

The graph holds 245,175 github people. Measured against the crawl:

    owners with a 100+ star repo    245,166
    people in the graph             245,175    <- a 9-person match

The population is exactly the 100-star floor. That was a defensible noise gate
when stars were the only signal available. But this graph's own headline finding
is that stars are a bad proxy -- dtolnay/unicode-ident carries 110 stars and
1,196,577,185 downloads -- and three independent sources now agree the floor
hides roughly half of everyone worth having.

WHY NOT JUST LOWER THE FLOOR. Because the floor is baked into the whole
pipeline, not just this loader:

    band      repos    rated    pct
    100+    478,907  226,963   47.4%
    10-99   893,266        0    0.0%
    under10     277        0    0.0%

The rating pass NEVER looked below 100 stars. Admitting that band wholesale
would grow the graph 3.6x and make it thinner -- 893k people with no quality
signal of any kind. That is a worse graph, not a bigger one.

THE RULE THIS USES INSTEAD: admit on external evidence of use. A crates.io
publisher is vouched for by download counts measured by a third party. That is
strictly better evidence than a star count and it does not require our rating
pass to have run. Measured candidates:

    crates.io users absent from the graph   59,297
      already crawled by us, below floor     9,896
      never seen anywhere                   49,401

WHAT IS CREATED. person rows with state='tracked' -- the schema's own provision
for "we care, nothing linked yet", written for the 9,395 registry people like
Andrew Ng who had zero content edges. They are real people with real published
software; they simply have no rated github work. kind stays 'unknown' rather
than guessed: crates.io accounts include bots and org accounts, and the honest
null is what person.kind exists to preserve.

A --min-downloads gate is available and defaults to 0. Anyone who publishes a
crate at all is a producer, which is the graph's membership rule, so the default
admits all of them; the gate exists for a caller who wants a stricter cut.
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
    return {
        "people_total": g.execute("SELECT COUNT(*) FROM person").fetchone()[0],
        "people_tracked": g.execute(
            "SELECT COUNT(*) FROM person WHERE state='tracked'").fetchone()[0],
        "crates_edges": g.execute(
            "SELECT COUNT(*) FROM person_content WHERE domain='crates'"
        ).fetchone()[0],
    }


def load(dump_dir, graph_db, apply_changes, min_downloads=0, limit=0):
    t0 = time.time()
    for f in ("users.csv", "crate_owners.csv", "crate_downloads.csv"):
        if not os.path.exists(os.path.join(dump_dir, f)):
            print(f"missing required file: {f}", file=sys.stderr)
            return None

    downloads = {}
    with open(os.path.join(dump_dir, "crate_downloads.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = (row.get("downloads") or "").strip()
            if d.isdigit():
                downloads[row["crate_id"]] = int(d)

    users = {}
    with open(os.path.join(dump_dir, "users.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            login = (row.get("gh_login") or "").strip()
            if row.get("id") and login:
                users[row["id"]] = (login, row.get("name") or login,
                                    row.get("gh_id") or "")

    # user -> crates owned, and their total measured downloads
    owned = defaultdict(list)
    with open(os.path.join(dump_dir, "crate_owners.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("owner_kind") or "").strip() != "0":
                continue
            uid, cid = row.get("owner_id"), row.get("crate_id")
            if uid in users and cid:
                owned[uid].append(cid)

    g = sqlite3.connect(graph_db)
    g.execute("PRAGMA busy_timeout=600000")
    before = counters(g)

    known = set()
    for (v,) in g.execute(
        "SELECT value FROM external_ids WHERE platform='github_login'"
    ):
        if v:
            known.add(v.strip().lower())
    have_person = {r[0] for r in g.execute("SELECT person_id FROM person")}

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    stats = {
        "candidates": 0,
        "already_in_graph": 0,
        "below_min_downloads": 0,
        "people_created": 0,
        "edges_created": 0,
        "ext_ids_created": 0,
    }
    people, edges, ext = [], [], []

    for uid, crates in owned.items():
        login, name, gh_id = users[uid]
        low = login.lower()
        stats["candidates"] += 1
        if low in known or f"gh:{login}" in have_person:
            stats["already_in_graph"] += 1
            continue
        total_dl = sum(downloads.get(c, 0) for c in crates)
        if total_dl < min_downloads:
            stats["below_min_downloads"] += 1
            continue
        if limit and stats["people_created"] >= limit:
            break
        pid = f"gh:{login}"
        # person columns are (person_id,name,sort_name,kind,state,merged_into,
        # birth_year,death_year,primary_tier,rank_score,origin,topics_json,
        # built_at) -- provenance is `origin`/`built_at` here, NOT the
        # source/observed_at pair person_content uses.
        people.append((
            pid, name, "unknown", "tracked", "crates_io", now,
            json.dumps({"admitted_on": "crates_io_publication",
                        "crates_owned": len(crates),
                        "crate_downloads_total": total_dl}),
        ))
        ext.append((pid, "github_login", login, 0.95, "crates_io"))
        if gh_id:
            ext.append((pid, "github_id", gh_id, 0.95, "crates_io"))
        ext.append((pid, "crates_io", uid, 0.95, "crates_io"))
        for cid in crates:
            edges.append((
                pid, "crates", cid, "owner", None, "crates_io", now,
                json.dumps({"crate_downloads": downloads.get(cid, 0)}),
            ))
        stats["people_created"] += 1

    stats["edges_created"] = len(edges)
    stats["ext_ids_created"] = len(ext)
    stats["before"] = before

    if apply_changes and people:
        g.executemany(
            "INSERT OR IGNORE INTO person "
            "(person_id,name,kind,state,origin,built_at,topics_json) "
            "VALUES (?,?,?,?,?,?,?)", people)
        g.executemany(
            "INSERT OR IGNORE INTO external_ids "
            "(person_id,platform,value,confidence,source) VALUES (?,?,?,?,?)",
            ext)
        g.executemany(
            "INSERT OR IGNORE INTO person_content "
            "(person_id,domain,content_ref,role,score,source,observed_at,meta_json) "
            "VALUES (?,?,?,?,?,?,?,?)", edges)
        g.commit()
        stats["after"] = counters(g)
    stats["applied"] = bool(apply_changes)
    stats["elapsed_s"] = round(time.time() - t0, 2)
    return stats


def main():
    ap = argparse.ArgumentParser(
        description="Admit crates.io publishers on evidence of use.")
    ap.add_argument("--dump", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--min-downloads", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    s = load(a.dump, a.graph, a.apply, a.min_downloads, a.limit)
    if s is None:
        return 1
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
