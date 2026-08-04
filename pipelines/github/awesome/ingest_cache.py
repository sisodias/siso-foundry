#!/usr/bin/env python3
"""Ingest EVERY cached README into the catalog, regardless of how it was found.

Why this exists (the load-bearing lesson from building this module):
  The original builder walks seed -> lists -> repos. That is a spanning tree
  rooted at one repo, and it turned out to be a severe sampling bias:
  measured, 73% of repos carrying topic:awesome / topic:awesome-list are NOT
  reachable from sindresorhus/awesome (2026-08-03: 492 of 672 topic-search
  results absent from the seed crawl's `list` table).

  Evidence that seed-only conclusions were sampling artifacts, not facts about
  the ecosystem -- counting DISTINCT lists citing each repo in the seed crawl:
    ggerganov/llama.cpp          0 lists
    openai/openai-python         0 lists
    anthropics/anthropic-sdk-py  0 lists
    langchain-ai/langchain       1 list
  ...while topic search finds 93 AI-era lists the seed never reaches, incl.
  PatrickJS/awesome-cursorrules (40k stars), e2b-dev/awesome-ai-agents (29k),
  github/awesome-copilot (37k). So "the corpus does not cover AI" was false;
  "the seed's neighbourhood does not cover AI" was the true statement.

  Note the seed is NOT unmaintained -- measured, seed-reachable lists are
  FRESHER than seed-missed ones (75% vs 60% pushed within a year). It is
  maintained but closed: entries stay current while new categories are not
  admitted, so the editorial gate that makes curation valuable is the same
  gate that makes it lag.

  So discovery and ingestion are separated. Anything that puts a README in
  .cache/ (seed crawl, topic search, depth-3 expansion, a hand-written list)
  becomes catalog input here. Discovery strategy is pluggable; ingestion is one
  code path.

Usage:
  ingest_cache.py --db catalog_full.sqlite --cache .cache [--min-links 20]
"""
import argparse
import json
import os
import sqlite3
import sys
import time

from build_awesome_catalog import (
    SCHEMA, parse_readme, topic_slug, is_list_readme, rollup, now,
)


def cached_repos(cache_dir):
    """Every owner__name.md in the cache -> ("owner/name", path)."""
    out = []
    for fn in sorted(os.listdir(cache_dir)):
        if not fn.endswith(".md") or "__" not in fn:
            continue
        stem = fn[:-3]
        owner, _, name = stem.partition("__")
        if not owner or not name:
            continue
        out.append((f"{owner}/{name}", os.path.join(cache_dir, fn)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="catalog_full.sqlite")
    ap.add_argument("--cache", default=".cache")
    ap.add_argument("--min-links", type=int, default=20)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)
    t0 = time.time()

    ingested = skipped = 0
    for repo, path in cached_repos(args.cache):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except Exception:
            continue

        # Classify by READING, never by name. A cached README that is not
        # shaped like a curated list is a target repo someone linked, not a
        # list -- skip it rather than polluting the catalog with its links.
        ok, st = is_list_readme(text, min_links=args.min_links)
        if not ok:
            skipped += 1
            continue

        # Reuse the parse the classifier already did -- it returns its entries
        # and title in the stats dict. Parsing twice was ~1/3 of ingest time.
        entries = st.get("entries")
        title = st.get("title")
        if entries is None:
            title, entries = parse_readme(text)
        pfile = path[:-3] + ".path"
        rpath = ""
        if os.path.exists(pfile):
            with open(pfile, encoding="utf-8") as f:
                rpath = f.read().strip()

        conn.execute(
            "INSERT OR REPLACE INTO list"
            "(list_repo,title,topic,depth,readme_path,n_entries,status,fetched_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (repo, title, topic_slug(repo), 1, rpath, len(entries), "ok", now()))
        conn.execute("DELETE FROM entry WHERE list_repo=?", (repo,))
        conn.executemany(
            "INSERT OR REPLACE INTO entry"
            "(list_repo,target_repo,section,section_path,description,position)"
            " VALUES(?,?,?,?,?,?)",
            [(repo, e["target"], e["section"], e["section_path"],
              e["description"], e["position"]) for e in entries])
        ingested += 1
        if ingested % 100 == 0:
            conn.commit()
            print(f"  ...{ingested} lists ingested", file=sys.stderr)

    conn.commit()
    rollup(conn)

    q = lambda s: conn.execute(s).fetchone()[0]
    print(json.dumps({
        "lists_ingested": ingested,
        "cached_not_lists": skipped,
        "entries": q("SELECT COUNT(*) FROM entry"),
        "unique_repos": q("SELECT COUNT(*) FROM repo"),
        "multi_list_repos": q("SELECT COUNT(*) FROM repo WHERE list_count>1"),
        "distinct_sections": q(
            "SELECT COUNT(DISTINCT section) FROM entry WHERE section IS NOT NULL"),
        "owners": q("SELECT COUNT(*) FROM owner_signal"),
        "elapsed_sec": round(time.time() - t0, 1),
        "db": os.path.abspath(args.db),
    }, indent=2))


if __name__ == "__main__":
    main()
