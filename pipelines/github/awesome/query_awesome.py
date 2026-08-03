#!/usr/bin/env python3
"""Read-side projections over awesome_catalog.sqlite.

Every "ranking" here is computed at read time from observed edges. Nothing in
the DB stores a verdict, so these are views, not facts -- change the query and
you change the ranking, without a migration.

Usage:
  query_awesome.py top        [--n 30]   most-cited repos (multi-list = signal)
  query_awesome.py owners     [--n 30]   people signal, by lists citing them
  query_awesome.py sections   [--n 30]   the inherited taxonomy, by volume
  query_awesome.py repo <owner/name>     everything known about one repo
  query_awesome.py stats                 catalog-wide counts
"""
import argparse
import json
import sqlite3
import sys

DB = "awesome_catalog.sqlite"


def connect(db):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def top(conn, n):
    return [dict(r) for r in conn.execute("""
        SELECT full_name, list_count, description
        FROM repo WHERE list_count > 1
        ORDER BY list_count DESC, full_name LIMIT ?""", (n,))]


def owners(conn, n):
    return [dict(r) for r in conn.execute("""
        SELECT owner, n_repos, n_lists, n_entries, max_repo_lists
        FROM owner_signal ORDER BY n_lists DESC, n_repos DESC LIMIT ?""", (n,))]


def sections(conn, n):
    """The inherited taxonomy: which headings humans actually use."""
    return [dict(r) for r in conn.execute("""
        SELECT section,
               COUNT(*)                    AS n_entries,
               COUNT(DISTINCT list_repo)   AS n_lists,
               COUNT(DISTINCT target_repo) AS n_repos
        FROM entry WHERE section IS NOT NULL
        GROUP BY section ORDER BY n_entries DESC LIMIT ?""", (n,))]


def alternatives(conn, full_name, n, language=None):
    """What do curators file ALONGSIDE this repo? -> a substitutes graph.

    Weighted by DISTINCT lists agreeing, never raw pair count: one 3,242-entry
    list puts hundreds of repos under a single heading and would otherwise
    dominate every result (measured: fzf's top "alternative" came back as
    ohmyzsh with 902 co-occurrences).

    Section names recur across ecosystems ("Validation" exists in both TS and
    Go lists), so pass language= when the caller cares about a stack.
    """
    sql = """
        SELECT b.target_repo AS repo,
               COUNT(DISTINCT a.list_repo) AS lists_agreeing,
               (SELECT language FROM repo r WHERE r.full_name=b.target_repo) AS language,
               (SELECT description FROM repo r WHERE r.full_name=b.target_repo) AS description
        FROM entry a
        JOIN entry b ON a.list_repo=b.list_repo AND a.section=b.section
                    AND b.target_repo<>a.target_repo
        WHERE a.target_repo=? AND a.section IS NOT NULL
          AND b.target_repo NOT IN (SELECT list_repo FROM list)
        GROUP BY b.target_repo
        HAVING COUNT(DISTINCT a.list_repo) > 1
        ORDER BY lists_agreeing DESC, repo LIMIT ?"""
    rows = [dict(r) for r in conn.execute(sql, (full_name, n * 4))]
    if language:
        rows = [r for r in rows if (r["language"] or "").lower() == language.lower()]
    return rows[:n]


def stale(conn, n, min_lists=2, years=3):
    """Curated but abandoned: the trap a star-sorted search walks into.

    Stars never decay, so past popularity keeps recommending dead projects.
    Requires --enrich or load_enrichment.py to have populated pushed_at.
    """
    return [dict(r) for r in conn.execute(f"""
        SELECT full_name, stars, substr(pushed_at,1,10) AS last_push,
               list_count, archived
        FROM repo
        WHERE pushed_at IS NOT NULL AND list_count >= ?
          AND pushed_at < date('now','-{int(years)} years')
          AND full_name NOT IN (SELECT list_repo FROM list)
        ORDER BY stars DESC LIMIT ?""", (min_lists, n))]


def repo_detail(conn, full_name):
    r = conn.execute("SELECT * FROM repo WHERE full_name=?", (full_name,)).fetchone()
    if not r:
        return {"error": f"{full_name} not in catalog"}
    cites = [dict(x) for x in conn.execute("""
        SELECT list_repo, section, section_path, description
        FROM entry WHERE target_repo=? ORDER BY list_repo""", (full_name,))]
    return {"repo": dict(r), "cited_by": cites}


def stats(conn):
    q = lambda s: conn.execute(s).fetchone()[0]
    return {
        "lists_ok": q("SELECT COUNT(*) FROM list WHERE status='ok'"),
        "lists_notfound": q("SELECT COUNT(*) FROM list WHERE status='notfound'"),
        "entries": q("SELECT COUNT(*) FROM entry"),
        "unique_repos": q("SELECT COUNT(*) FROM repo"),
        "multi_list_repos": q("SELECT COUNT(*) FROM repo WHERE list_count>1"),
        "pct_multi_list": round(100.0 * q("SELECT COUNT(*) FROM repo WHERE list_count>1")
                                / max(1, q("SELECT COUNT(*) FROM repo")), 2),
        "max_list_count": q("SELECT COALESCE(MAX(list_count),0) FROM repo"),
        "distinct_sections": q("SELECT COUNT(DISTINCT section) FROM entry WHERE section IS NOT NULL"),
        "pct_entries_with_section": round(
            100.0 * q("SELECT COUNT(*) FROM entry WHERE section IS NOT NULL")
            / max(1, q("SELECT COUNT(*) FROM entry")), 2),
        "pct_entries_with_description": round(
            100.0 * q("SELECT COUNT(*) FROM entry WHERE description IS NOT NULL")
            / max(1, q("SELECT COUNT(*) FROM entry")), 2),
        "owners": q("SELECT COUNT(*) FROM owner_signal"),
        "owners_multi_list": q("SELECT COUNT(*) FROM owner_signal WHERE n_lists>1"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["top", "owners", "sections", "repo",
                                    "stats", "alternatives", "stale"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--db", default=DB)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--language", help="alternatives: restrict to one stack")
    ap.add_argument("--min-lists", type=int, default=2, help="stale: min citations")
    ap.add_argument("--years", type=int, default=3, help="stale: untouched for N years")
    a = ap.parse_args()

    conn = connect(a.db)
    if a.cmd == "top":
        out = top(conn, a.n)
    elif a.cmd == "owners":
        out = owners(conn, a.n)
    elif a.cmd == "sections":
        out = sections(conn, a.n)
    elif a.cmd == "stats":
        out = stats(conn)
    elif a.cmd == "stale":
        out = stale(conn, a.n, a.min_lists, a.years)
    elif a.cmd == "alternatives":
        if not a.arg:
            print("alternatives needs owner/name", file=sys.stderr)
            sys.exit(2)
        out = alternatives(conn, a.arg, a.n, a.language)
    else:
        if not a.arg:
            print("repo needs owner/name", file=sys.stderr)
            sys.exit(2)
        out = repo_detail(conn, a.arg)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
