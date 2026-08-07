#!/usr/bin/env python3
"""
Attach crates.io ARTIFACT-LEVEL signal to github edges, joined by repository URL.

WHY THIS EXISTS, given load_crates_maintainers.py already ran.

That loader joins crates.io users to people (gh_login -> 'gh:<login>') and
writes domain='crates' edges. It answers "who maintains crates". It cannot
answer "is the repo we already rated actually installed by anyone", because a
person-level join never touches the repo.

83% of crates declare a `repository`, and 78% of those point at github.com. That
is a DIRECT artifact join onto repo_card.full_name -- the same key the whole
github domain is already indexed on. Measured against the 2026-08-04 dump:

    crates scanned                     310,628
    crate->repo matched our crawl       53,193
    of which already rated              24,517

24,517 repos hold a human-assigned overall_value AND can now carry a real
install count. Stars are a vote and ratings are an opinion; downloads are a
measurement. This is the same fame-vs-value inversion that surfaced
yargs/yargs-parser (517 stars, 4.4M dependents), computed on ground truth for
a whole language ecosystem rather than inferred.

WHAT IS WRITTEN, and what is deliberately not.

Written into person_content.meta_json for domain='github' edges whose
content_ref matches a crate's repository URL:

    crate_name        the crate published from this repo
    crate_downloads   all-time downloads (crate_downloads.csv, not crates.csv --
                      crates.csv has NO downloads column; assuming it did is what
                      left crates_downloads_known at 0 in the first run)
    crate_versions    how many releases exist
    crate_yanked      how many were withdrawn by the author -- a NEGATIVE quality
                      signal the graph has no other source for
    crate_edition     latest declared Rust edition (modernity)
    crate_license     declared license of the latest version

NOT written: `score` is never touched. Stars stay stars. A download count is a
different claim from a star count and merging them destroys the comparison that
makes either interesting -- the same reasoning load_repo_value.py used when it
put value in meta_json rather than over score.

ONE CRATE PER REPO. A monorepo can publish many crates from one repository. We
keep the most-downloaded one and record crate_count_at_repo alongside, rather
than writing N conflicting rows onto one edge or silently taking the first.

Counters use json_extract, never `meta_json LIKE '%key%'` -- LIKE matches VALUES
as well as keys and previously reported a baseline of 35 where the truth was 0.
"""

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
import time

# crates.csv embeds full README text in a single field.
csv.field_size_limit(10 ** 9)

GITHUB_URL = re.compile(r"github\.com[/:]([^/\s]+)/([^/\s#?]+)", re.I)


def repo_from_url(url):
    """github.com/OWNER/REPO in any shape -> 'owner/repo', else None."""
    if not url:
        return None
    m = GITHUB_URL.search(url)
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    repo = repo.removesuffix(".git")
    if not owner or not repo:
        return None
    return f"{owner}/{repo}".lower()


def connect_rw(path):
    con = sqlite3.connect(path)
    con.execute("PRAGMA busy_timeout=600000")
    return con


def counters(g):
    def n(key):
        return g.execute(
            "SELECT COUNT(*) FROM person_content WHERE domain='github' "
            f"AND json_extract(meta_json,'$.{key}') IS NOT NULL"
        ).fetchone()[0]
    return {
        "edges_with_crate_name": n("crate_name"),
        "edges_with_crate_downloads": n("crate_downloads"),
        "edges_with_crate_yanked": n("crate_yanked"),
    }


def load(dump_dir, graph_db, apply_changes, limit=0):
    t0 = time.time()
    need = ["crates.csv", "crate_downloads.csv", "versions.csv"]
    for f in need:
        p = os.path.join(dump_dir, f)
        if not os.path.exists(p):
            print(f"missing required file: {p}", file=sys.stderr)
            return None

    # --- downloads per crate_id (the file the first loader never opened) -----
    downloads = {}
    with open(os.path.join(dump_dir, "crate_downloads.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = (row.get("downloads") or "").strip()
            if d.isdigit():
                downloads[row["crate_id"]] = int(d)

    # --- per-crate version rollup: count, yanked, latest edition/license -----
    ver_count, yanked, edition, license_ = {}, {}, {}, {}
    with open(os.path.join(dump_dir, "versions.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = row.get("crate_id")
            if not cid:
                continue
            ver_count[cid] = ver_count.get(cid, 0) + 1
            if (row.get("yanked") or "").strip() in ("t", "true", "1"):
                yanked[cid] = yanked.get(cid, 0) + 1
            # created_at ordering is not guaranteed in the dump; last non-empty
            # wins, which is good enough for a modernity hint and is recorded
            # as such rather than as "the latest release".
            if row.get("edition"):
                edition[cid] = row["edition"]
            if row.get("license"):
                license_[cid] = row["license"]

    # --- crate -> github repo, keeping the most-downloaded per repo ---------
    best = {}          # repo_full_name(lower) -> (downloads, crate_id, name)
    at_repo = {}       # repo -> how many crates published from it
    scanned = 0
    with open(os.path.join(dump_dir, "crates.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            scanned += 1
            repo = repo_from_url(row.get("repository"))
            if not repo:
                continue
            cid = row.get("id")
            dl = downloads.get(cid, 0)
            at_repo[repo] = at_repo.get(repo, 0) + 1
            cur = best.get(repo)
            if cur is None or dl > cur[0]:
                best[repo] = (dl, cid, row.get("name") or "")

    g = connect_rw(graph_db)
    before = counters(g)

    # github edges are keyed by repo full_name in content_ref.
    edges = {}
    for pid, ref, meta in g.execute(
        "SELECT person_id, content_ref, meta_json FROM person_content "
        "WHERE domain='github'"
    ):
        if ref:
            edges.setdefault(ref.lower(), []).append((pid, ref, meta))

    stats = {
        "crates_scanned": scanned,
        "crates_with_github_repo": len(at_repo),
        "repos_matched_in_graph": 0,
        "edges_updated": 0,
        "monorepo_repos": sum(1 for v in at_repo.values() if v > 1),
    }

    updates = []
    for repo, (dl, cid, cname) in best.items():
        rows = edges.get(repo)
        if not rows:
            continue
        stats["repos_matched_in_graph"] += 1
        if limit and stats["repos_matched_in_graph"] > limit:
            break
        for pid, ref, meta in rows:
            try:
                m = json.loads(meta) if meta else {}
            except Exception:
                m = {}
            m["crate_name"] = cname
            m["crate_downloads"] = dl
            m["crate_versions"] = ver_count.get(cid, 0)
            m["crate_yanked"] = yanked.get(cid, 0)
            if edition.get(cid):
                m["crate_edition"] = edition[cid]
            if license_.get(cid):
                m["crate_license"] = license_[cid]
            if at_repo.get(repo, 1) > 1:
                m["crate_count_at_repo"] = at_repo[repo]
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
        description="Attach crates.io artifact signal to github edges by repo URL."
    )
    ap.add_argument("--dump", required=True,
                    help="extracted crates.io dump data/ directory")
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
