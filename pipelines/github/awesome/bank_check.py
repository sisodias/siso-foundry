#!/usr/bin/env python3
"""bank-check — "has someone already solved this, and is it still alive?"

Complements `foundry repos "<query>"`, which ranks by STARS. Stars are a
permanent record of past popularity and never decay, so a star-ranked answer
confidently recommends abandoned projects. Measured 2026-08-04 on this corpus:
28.1% of peer-validated repos are >3y untouched, including atom/atom (60,807
stars, still cited by 30 curated lists) and phantomjs (29,453 stars, archived).

This adds three things stars cannot express:

  PEER VALIDATION  how many INDEPENDENT curated lists chose it. A repo picked
                   by 12 unrelated maintainers is a different claim than one
                   with 12k stars from a single HN front page.
  LIVENESS         pushed_at / archived, so dead-but-famous is visible.
  ALTERNATIVES     what curators file UNDER THE SAME HEADING -- a substitutes
                   graph no GitHub metadata field encodes.

Usage:
  bank_check.py "task queue"                 # what should I use for X?
  bank_check.py --alts junegunn/fzf          # what competes with X?
  bank_check.py "vector database" --json
"""
import argparse
import json
import os
import sqlite3
import sys

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "catalog_full.sqlite")


def _liveness(pushed, archived):
    if archived:
        return "ARCHIVED"
    if not pushed:
        return "unknown"
    y = pushed[:4]
    try:
        import datetime
        age = (datetime.date.today() - datetime.date.fromisoformat(pushed[:10])).days / 365.25
    except Exception:
        return "unknown"
    if age < 1:
        return "active"
    if age < 3:
        return f"stale {age:.0f}y"
    return f"DEAD {age:.0f}y"


def search_fts(conn, query, n):
    """FTS5 over curated sections+descriptions. Returns [] if no index.

    Measured 2026-08-04 (EVALUATION.md): the LIKE fallback below matched
    substrings blindly -- "job scheduler" returned `gron` (a JSON tool),
    "rate limiting" returned LLM gateways whose descriptions merely mention
    it. FTS5 with porter stemming ranks by relevance instead, and requires
    every term to appear rather than any substring.
    """
    try:
        conn.execute("SELECT 1 FROM repo_fts LIMIT 1")
    except sqlite3.OperationalError:
        return None                      # index not built; caller falls back
    # AND every term: "task queue" must match both, not either.
    terms = " AND ".join(f'"{t}"' for t in query.split() if t)
    if not terms:
        return []
    rows = conn.execute("""
        SELECT f.full_name,
               (SELECT COUNT(DISTINCT list_repo) FROM entry
                 WHERE target_repo = f.full_name) AS lists,
               (SELECT description FROM entry
                 WHERE target_repo = f.full_name AND description IS NOT NULL
                 LIMIT 1) AS curated_desc,
               r.stars, r.language, r.pushed_at, r.archived
        FROM repo_fts f
        LEFT JOIN repo r ON r.full_name = f.full_name
        WHERE repo_fts MATCH ?
        -- Rank by RELEVANCE, with citations only as a mild tiebreak.
        -- A first attempt used `bm25 - lists*0.5`, which let popularity swamp
        -- the match: modelcontextprotocol/servers (99 lists) topped "job
        -- scheduler", "rate limiting" AND "web scraping". bm25 is negative
        -- (lower = better), so the log term nudges without dominating.
        ORDER BY bm25(repo_fts) - (CASE WHEN lists > 1
                                        THEN min(lists, 20) * 0.05 ELSE 0 END)
        LIMIT ?""", (terms, n)).fetchall()
    return [dict(r) for r in rows]


def search(conn, query, n):
    """Repos curators filed under a heading or described matching `query`."""
    q = f"%{query.lower()}%"
    rows = conn.execute("""
        SELECT e.target_repo AS full_name,
               COUNT(DISTINCT e.list_repo) AS lists,
               MIN(e.description)          AS curated_desc,
               r.stars, r.language, r.pushed_at, r.archived
        FROM entry e
        LEFT JOIN repo r ON r.full_name = e.target_repo
        WHERE (lower(e.section) LIKE ? OR lower(e.description) LIKE ?)
          AND e.target_repo NOT IN (SELECT list_repo FROM list)
        GROUP BY e.target_repo
        ORDER BY lists DESC, r.stars DESC
        LIMIT ?""", (q, q, n)).fetchall()
    return [dict(r) for r in rows]


def alternatives(conn, repo, n):
    """Co-placement: what do curators file under the SAME heading as `repo`?"""
    rows = conn.execute("""
        SELECT b.target_repo AS full_name,
               COUNT(DISTINCT a.list_repo) AS lists,
               r.stars, r.language, r.pushed_at, r.archived,
               (SELECT description FROM entry x
                 WHERE x.target_repo = b.target_repo AND x.description IS NOT NULL
                 LIMIT 1) AS curated_desc
        FROM entry a
        JOIN entry b ON a.list_repo = b.list_repo AND a.section = b.section
                    AND b.target_repo <> a.target_repo
        LEFT JOIN repo r ON r.full_name = b.target_repo
        WHERE a.target_repo = ? AND a.section IS NOT NULL
          AND b.target_repo NOT IN (SELECT list_repo FROM list)
        GROUP BY b.target_repo
        HAVING COUNT(DISTINCT a.list_repo) > 1
        ORDER BY lists DESC, r.stars DESC
        LIMIT ?""", (repo, n)).fetchall()
    return [dict(r) for r in rows]


def render(rows, header):
    if not rows:
        print("NOT FOUND", file=sys.stderr)
        return 3
    print(f"# {header}")
    for r in rows:
        live = _liveness(r.get("pushed_at"), r.get("archived"))
        flag = "  ⚠" if live.startswith(("DEAD", "ARCHIVED")) else ""
        stars = f"{r['stars']:,}★" if r.get("stars") else "—"
        print(f"  {r['full_name']:<42} {r['lists']:>3} lists  {stars:>9}  "
              f"{(r.get('language') or '—'):<12} {live}{flag}")
        d = (r.get("curated_desc") or "").strip().replace("\n", " ")
        if d:
            print(f"      {d[:96]}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", help='e.g. "task queue"')
    ap.add_argument("--alts", metavar="OWNER/REPO",
                    help="what competes with this repo")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("-n", type=int, default=12)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fts", action="store_true",
                    help="use the FTS5 index instead of LIKE (scores WORSE "
                         "on the EVALUATION.md benchmark: 15/75 vs 31/75)")
    a = ap.parse_args()

    if not a.query and not a.alts:
        ap.error("give a query or --alts OWNER/REPO")
    if not os.path.exists(a.db):
        print(f"catalog not found: {a.db}", file=sys.stderr)
        return 4

    conn = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    if a.alts:
        rows = alternatives(conn, a.alts, a.n)
        header = f"alternatives to {a.alts} (by independent lists agreeing)"
    else:
        # LIKE + citation ranking is the DEFAULT because it measures better.
        # Blind A/B on 15 questions (EVALUATION.md): LIKE 31/75, FTS5 15/75.
        # FTS5's bm25 rewards SHORT documents, so it surfaces obscure repos
        # with terse descriptions over the well-known tools people want --
        # "full text search" returned Flask plugins instead of elasticsearch.
        # Three different bm25/citation weightings all scored worse. Kept
        # behind --fts because the index is built and the failure is in the
        # ranking, not the data; someone should revisit with a better scorer.
        if a.fts:
            rows = search_fts(conn, a.query, a.n)
            if rows is None:
                print("no FTS index; run the builder in EVALUATION.md",
                      file=sys.stderr)
                return 4
            header = f"peer-validated repos for '{a.query}' (FTS5)"
        else:
            rows = search(conn, a.query, a.n)
            header = f"peer-validated repos for '{a.query}'"

    if a.json:
        print(json.dumps(rows, indent=2))
        return 0 if rows else 3
    return render(rows, header)


if __name__ == "__main__":
    sys.exit(main())
