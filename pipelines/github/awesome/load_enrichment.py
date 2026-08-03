#!/usr/bin/env python3
"""Load a JSONL of GitHub repo metadata into the catalog's repo table.

Why a separate loader: bulk metadata fetching is embarrassingly parallel and
best done by a fleet of cheap workers writing JSONL, not by the builder's
serial --enrich loop. This folds their output back in so the liveness analysis
is reproducible FROM THE DB rather than from a side file.

Accepts concatenated JSON (pretty-printed or one-per-line) -- `gh api --jq`
emits multi-line objects, so a naive line-by-line json.loads fails on it.

Usage: load_enrichment.py --db catalog_full.sqlite --jsonl /tmp/enriched.jsonl
"""
import argparse
import json
import sqlite3
import time


def parse_stream(path):
    """Yield objects from concatenated JSON, pretty-printed or not."""
    raw = open(path, encoding="utf-8").read()
    dec = json.JSONDecoder()
    i, n = 0, len(raw)
    while i < n:
        while i < n and raw[i] in " \n\r\t":
            i += 1
        if i >= n:
            break
        try:
            obj, j = dec.raw_decode(raw, i)
            yield obj
            i = j
        except json.JSONDecodeError:
            i += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="catalog_full.sqlite")
    ap.add_argument("--jsonl", default="/tmp/enriched.jsonl")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    # Tolerate a DB created before the liveness columns existed.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(repo)")}
    for col, decl in (("pushed_at", "TEXT"), ("archived", "INTEGER"),
                      ("created_at", "TEXT")):
        if col not in cols:
            conn.execute(f"ALTER TABLE repo ADD COLUMN {col} {decl}")

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    seen, updated, unknown = set(), 0, 0
    for o in parse_stream(args.jsonl):
        full = o.get("full_name")
        if not full or full in seen:
            continue
        seen.add(full)
        cur = conn.execute(
            "UPDATE repo SET stars=?, language=?,"
            " description=COALESCE(description,?), topics_json=?,"
            " pushed_at=?, archived=?, created_at=?, enriched_at=?"
            " WHERE full_name=?",
            (o.get("stars"), o.get("language"), o.get("description"),
             json.dumps(o.get("topics") or []), o.get("pushed_at"),
             1 if o.get("archived") else 0, o.get("created_at"), now, full))
        if cur.rowcount:
            updated += 1
        else:
            unknown += 1          # in the JSONL but not (yet) in this catalog
    conn.commit()

    q = lambda s: conn.execute(s).fetchone()[0]
    print(json.dumps({
        "records_read": len(seen),
        "repos_updated": updated,
        "not_in_catalog": unknown,
        "repos_with_pushed_at": q("SELECT COUNT(*) FROM repo WHERE pushed_at IS NOT NULL"),
        "archived": q("SELECT COUNT(*) FROM repo WHERE archived=1"),
    }, indent=2))


if __name__ == "__main__":
    main()
