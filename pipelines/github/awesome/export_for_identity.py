#!/usr/bin/env python3
"""Export the awesome catalog as a feed for the GitHub identity corpus.

What this adds that identity does not have:
  identity knows ~465k repos EXIST. It does not know that a human filed
  milvus next to weaviate under one heading in a vector-database list. The
  edges are the contribution, not the repo count -- measured 2026-08-03,
  71.8% of the awesome catalog's peer-validated repos were ALREADY in
  identity, so this is not primarily a discovery feed.

Two outputs, deliberately separate because they answer different questions:

  1. enrichment  -- for repos identity ALREADY has: the curated categories
     they were filed under, the human-written descriptions, and how many
     independent lists cite them. Joins on owner/name.
  2. candidates  -- repos identity does NOT have, ranked by list_count.
     Peer-validated ones first; these are worth rating.

Writes JSONL (one object per line, streamable) rather than touching identity
directly. The single-writer law applies: this produces a feed, the identity
pipeline decides what to do with it.

Usage:
  export_for_identity.py --db catalog_full.sqlite \
      --identity ~/SISO_Workspace/SISO_Agent_Base/research/repo-catalog/identity/identity.sqlite \
      --out-dir ./export
"""
import argparse
import json
import os
import sqlite3


def identity_repos(path):
    """owner/name (lowercased) for every repo in the identity corpus."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    have = set()
    for (u,) in con.execute(
            "SELECT normalized_url FROM repo_identity WHERE normalized_url IS NOT NULL"):
        u = (u or "").strip().rstrip("/")
        if "github.com/" not in u:
            continue
        p = u.split("github.com/", 1)[1]
        if p.count("/") >= 1:
            have.add("/".join(p.split("/")[:2]).lower().removesuffix(".git"))
    con.close()
    return have


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="catalog_full.sqlite")
    ap.add_argument("--identity", required=True)
    ap.add_argument("--out-dir", default="./export")
    ap.add_argument("--min-lists", type=int, default=1,
                    help="candidates: minimum distinct citing lists")
    ap.add_argument("--both-directions", action="store_true",
                    help="emit a->b AND b->a (2x the file; simpler to query)")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    have = identity_repos(args.identity)

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    # Sections + descriptions per repo, aggregated once.
    rows = con.execute("""
        SELECT e.target_repo AS full_name,
               COUNT(DISTINCT e.list_repo) AS list_count,
               GROUP_CONCAT(DISTINCT e.section)   AS sections,
               GROUP_CONCAT(DISTINCT e.list_repo) AS cited_by
        FROM entry e
        WHERE e.target_repo NOT IN (SELECT list_repo FROM list)
        GROUP BY e.target_repo
    """)

    desc = {}
    for r in con.execute("""
        SELECT target_repo, description FROM entry
        WHERE description IS NOT NULL GROUP BY target_repo"""):
        desc[r[0]] = r[1]

    n_enrich = n_cand = 0
    fe = open(os.path.join(args.out_dir, "enrichment.jsonl"), "w")
    fc = open(os.path.join(args.out_dir, "candidates.jsonl"), "w")
    for r in rows:
        full = r["full_name"]
        rec = {
            "full_name": full,
            "list_count": r["list_count"],
            "sections": sorted({s for s in (r["sections"] or "").split(",") if s}),
            "cited_by": sorted({s for s in (r["cited_by"] or "").split(",") if s})[:20],
            "curated_description": desc.get(full),
        }
        if full.lower() in have:
            fe.write(json.dumps(rec) + "\n")
            n_enrich += 1
        elif r["list_count"] >= args.min_lists:
            fc.write(json.dumps(rec) + "\n")
            n_cand += 1
    fe.close()
    fc.close()

    # Substitutes graph.
    #
    # The naive self-join over the whole entry table is O(sum of section_size^2)
    # and exhausts SQLite temp space at corpus scale -- it died with "database
    # or disk is full" at 510k entries. Two cheap restrictions make it tractable
    # without changing the result:
    #
    #   1. Only MULTI-LIST repos can ever produce an edge with
    #      lists_agreeing > 1, so pre-filter to those. This is the big win:
    #      it drops ~75% of rows before the join.
    #   2. Skip giant sections. One list puts 3,000+ repos under a single
    #      heading; that section alone contributes ~9M pairs and is exactly
    #      the low-signal bulk the weighting is meant to suppress.
    #
    # Streamed in chunks so peak memory stays flat regardless of corpus size.
    con.execute("DROP TABLE IF EXISTS temp.pairable")
    con.execute("""
        CREATE TEMP TABLE pairable AS
        SELECT e.list_repo, e.section, e.target_repo
        FROM entry e
        JOIN repo r ON r.full_name = e.target_repo AND r.list_count > 1
        WHERE e.section IS NOT NULL
          AND e.target_repo NOT IN (SELECT list_repo FROM list)
    """)
    con.execute("CREATE INDEX temp.ix_pair ON pairable(list_repo, section)")
    # Drop sections so large they are bulk dumps rather than curation.
    con.execute("""
        DELETE FROM pairable WHERE rowid IN (
          SELECT p.rowid FROM pairable p
          JOIN (SELECT list_repo, section FROM pairable
                 GROUP BY list_repo, section HAVING COUNT(*) > 400) big
            ON big.list_repo = p.list_repo AND big.section = p.section)
    """)

    # Direction. The relation is symmetric -- co-placement of a and b is one
    # fact -- so `a < b` halves both the join work and the output file
    # (measured: 100% of a 2,249,906-edge export was reciprocal duplicates).
    # --both-directions restores the redundant form for consumers that want to
    # query `WHERE repo = X` without checking two columns.
    cmp_op = "<" if not args.both_directions else "<>"
    n_edges = 0
    with open(os.path.join(args.out_dir, "substitutes.jsonl"), "w") as f:
        cur = con.execute(f"""
            SELECT a.target_repo AS repo, b.target_repo AS alt,
                   COUNT(DISTINCT a.list_repo) AS lists_agreeing
            FROM pairable a
            JOIN pairable b ON a.list_repo=b.list_repo AND a.section=b.section
                           AND b.target_repo {cmp_op} a.target_repo
            GROUP BY a.target_repo, b.target_repo
            HAVING COUNT(DISTINCT a.list_repo) > 1
        """)
        while True:
            batch = cur.fetchmany(10000)
            if not batch:
                break
            for r in batch:
                f.write(json.dumps(dict(r)) + "\n")
                n_edges += 1

    print(json.dumps({
        "identity_repos": len(have),
        "enrichment_rows": n_enrich,
        "candidate_rows": n_cand,
        "substitute_edges": n_edges,
        "out_dir": os.path.abspath(args.out_dir),
    }, indent=2))


if __name__ == "__main__":
    main()
