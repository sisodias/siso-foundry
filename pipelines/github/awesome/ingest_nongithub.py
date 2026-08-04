#!/usr/bin/env python3
"""Ingest curated lists whose entries are NOT GitHub repos.

The main pipeline's LINK_RE matches github.com only, so a list curating
websites, papers, videos or hosted tools parses as ~0 links and is rejected as
"not a list". Measured 2026-08-04: of 8,435 rejected READMEs, 2,535 (30%) have
20+ markdown bullet links to non-github URLs -- real curation the repo-oriented
parser structurally cannot see. Confirmed by sampling: awesome-amsterdam,
awesome-brazilian-youtubers, awesome-omnigraffle, awesome-agent-economy.

This writes to a SEPARATE table (`weblink`) in the SAME database rather than
widening `entry`. Two reasons:
  * `entry.target_repo` is a join key into the GitHub identity corpus. Putting
    URLs in it would break every existing consumer.
  * A website citation and a repo citation are different evidence. Keeping
    them apart lets a caller ask for either without filtering.

Reads the same .cache/ as everything else -- discovery stays pluggable.

Usage: ingest_nongithub.py --db catalog_full.sqlite --cache .cache
"""
import argparse
import json
import os
import re
import sqlite3
import time
from urllib.parse import urlparse

from build_awesome_catalog import HEADING_RE, now

SCHEMA = """
CREATE TABLE IF NOT EXISTS weblist (
  list_repo  TEXT PRIMARY KEY,
  title      TEXT,
  n_links    INTEGER,
  fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS weblink (
  list_repo   TEXT NOT NULL,
  url         TEXT NOT NULL,
  domain      TEXT NOT NULL,      -- the dedup/aggregation key
  label       TEXT,               -- the link text
  section     TEXT,
  description TEXT,
  position    INTEGER NOT NULL,
  PRIMARY KEY (list_repo, url, position)
);
CREATE INDEX IF NOT EXISTS ix_weblink_domain  ON weblink(domain);
CREATE INDEX IF NOT EXISTS ix_weblink_list    ON weblink(list_repo);
CREATE INDEX IF NOT EXISTS ix_weblink_section ON weblink(section);
"""

# "- [label](url) - description" -- the standard awesome entry shape.
ENTRY_RE = re.compile(
    r"^[-*+]\s+\[([^\]]+)\]\((https?://[^)\s]+)\)\s*(?:[-–—:]\s*(.*))?$")

# Hosts that are never a curated resource: badges, CDNs, the awesome badge
# itself, and github (which the main pipeline already owns).
SKIP_HOSTS = {
    "github.com", "www.github.com", "raw.githubusercontent.com",
    "user-images.githubusercontent.com", "camo.githubusercontent.com",
    "img.shields.io", "shields.io", "badgen.net", "cdn.jsdelivr.net",
    "travis-ci.org", "travis-ci.com", "circleci.com", "codecov.io",
    "awesome.re", "forthebadge.com", "badge.fury.io",
}


def parse_weblinks(text):
    """-> (title, [entry dicts]) for non-github bullet links."""
    title, stack, out, pos = None, {}, [], 0
    in_code = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_code = not in_code
            continue
        if in_code:
            continue
        h = HEADING_RE.match(s)
        if h:
            lvl = len(h.group(1))
            txt = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", h.group(2)).strip()
            txt = re.sub(r"<[^>]+>", " ", txt)
            txt = re.sub(r"\s+", " ", txt).strip(" #*_-·|")
            if lvl == 1 and title is None:
                title = txt
            stack[lvl] = txt
            for d in [k for k in stack if k > lvl]:
                del stack[d]
            continue
        m = ENTRY_RE.match(s)
        if not m:
            continue
        label, url, desc = m.group(1), m.group(2), m.group(3)
        host = (urlparse(url).hostname or "").lower()
        if not host or host in SKIP_HOSTS or host.endswith(".githubusercontent.com"):
            continue
        levels = sorted(k for k in stack if k > 1)
        out.append({
            "url": url.rstrip(").,"),
            "domain": host[4:] if host.startswith("www.") else host,
            "label": re.sub(r"<[^>]+>", "", label).strip(),
            "section": stack[levels[-1]] if levels else None,
            "description": (desc or "").strip() or None,
            "position": pos,
        })
        pos += 1
    return title, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="catalog_full.sqlite")
    ap.add_argument("--cache", default=".cache")
    ap.add_argument("--min-links", type=int, default=20)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)

    # Only consider READMEs the GitHub pipeline did NOT already accept.
    already = {r[0] for r in conn.execute("SELECT list_repo FROM list")}

    t0, n_lists, n_links = time.time(), 0, 0
    for fn in sorted(os.listdir(args.cache)):
        if not fn.endswith(".md") or "__" not in fn:
            continue
        repo = fn[:-3].replace("__", "/", 1)
        if repo in already:
            continue
        try:
            with open(os.path.join(args.cache, fn), encoding="utf-8",
                      errors="replace") as f:
                text = f.read()
        except Exception:
            continue
        title, links = parse_weblinks(text)
        if len(links) < args.min_links:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO weblist(list_repo,title,n_links,fetched_at)"
            " VALUES(?,?,?,?)", (repo, title, len(links), now()))
        conn.execute("DELETE FROM weblink WHERE list_repo=?", (repo,))
        conn.executemany(
            "INSERT OR REPLACE INTO weblink"
            "(list_repo,url,domain,label,section,description,position)"
            " VALUES(?,?,?,?,?,?,?)",
            [(repo, l["url"], l["domain"], l["label"], l["section"],
              l["description"], l["position"]) for l in links])
        n_lists += 1
        n_links += len(links)
        if n_lists % 200 == 0:
            conn.commit()
    conn.commit()

    q = lambda s: conn.execute(s).fetchone()[0]
    print(json.dumps({
        "weblists": n_lists,
        "weblinks": n_links,
        "distinct_domains": q("SELECT COUNT(DISTINCT domain) FROM weblink"),
        "multi_list_domains": q(
            "SELECT COUNT(*) FROM (SELECT domain FROM weblink"
            " GROUP BY domain HAVING COUNT(DISTINCT list_repo)>1)"),
        "elapsed_sec": round(time.time() - t0, 1),
    }, indent=2))


if __name__ == "__main__":
    main()
