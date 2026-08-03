#!/usr/bin/env python3
"""Build a per-BOOK passage summary instead of a per-PASSAGE table.

WHY THIS EXISTS
---------------
build_passages.py writes one row per passage. Measured on this corpus that is
~590 passages per book, and the table costs ~394 KB/book:

    2,000 books -> 1,188,761 passages -> 788 MB
    projected at 77,540 books        -> ~30.6 GB

The mini has 25 GB free, so a full build cannot complete -- which is very likely
what produced the `sqlite3.OperationalError: disk I/O error` that killed the
original run at 500 books while still logging "passages done".

But the people graph does not consume passages. `load_passage_signal.py` reads
exactly this:

    SELECT gid, COUNT(*), SUM(words), MIN(heading) FROM passage GROUP BY gid

A per-book rollup. Writing 590 rows to derive 1 is the wrong shape: it is ~590x
the storage for information the consumer immediately aggregates away.

This builds the rollup directly while streaming the tar, never materialising the
passage rows. Same numbers reaching the graph, ~3 orders of magnitude less disk.

WHAT IS GIVEN UP, STATED PLAINLY. Per-passage byte offsets are what make
"retrieve THIS paragraph by range" work -- the whole point of the passages
design. This summary CANNOT do that. It is the right structure for the people
graph's question ("how much readable text does this person have") and the wrong
one for retrieval. If passage-level retrieval is wanted later, build it per-book
on demand from the tar, or run the full build somewhere with 40 GB free. Both
are cheap; a 30 GB table that cannot fit is not.

Reuses build_passages.py's own segmentation functions so the counts are
identical to what the full table would have produced -- not a reimplementation
that could drift.

Usage:
  build_passage_summary.py --tar txt-files.tar --db passage_summary.sqlite [--limit N]
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import tarfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Reuse the REAL segmentation rather than approximating it. A first draft here
# split on blank lines only and produced 704,697 "passages" for the same 500
# books where build_passages.py produces 295,646 -- 2.4x off, because the real
# splitter MERGES short blocks up to MIN_CHARS, splits oversized ones at
# MAX_CHARS on sentence boundaries, and trims Gutenberg boilerplate via
# body_bounds(). Importing guarantees the counts are identical and cannot drift.
from build_passages import (  # noqa: E402
    body_bounds, headings_index, split_passages,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS book_passages (
  gid            INTEGER PRIMARY KEY,
  passage_count  INTEGER NOT NULL,
  word_count     INTEGER NOT NULL,
  char_count     INTEGER NOT NULL,
  first_heading  TEXT,
  built_at       TEXT NOT NULL
);
"""

GID_RE = re.compile(r"(\d+)")


def summarise(text):
    """Per-book rollup, byte-identical to what build_passages.py would emit."""
    start, end = body_bounds(text)
    spans = split_passages(text, start, end)
    heads = headings_index(text, start, end)

    n, words, chars = 0, 0, 0
    for a, b in spans:
        chunk = text[a:b].strip()
        if not chunk:
            continue
        n += 1
        words += len(chunk.split())
        chars += b - a
    first_heading = heads[0][1][:120] if heads else None
    return n, words, chars, first_heading


def build(tar_path, db_path, limit):
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    done = {g for (g,) in con.execute("SELECT gid FROM book_passages")}
    rows, books, skipped = [], 0, 0

    with tarfile.open(tar_path, "r|*") as tf:
        for info in tf:
            if not info.isfile() or not info.name.endswith(".txt"):
                continue
            m = GID_RE.search(os.path.basename(info.name))
            if not m:
                continue
            gid = int(m.group(1))
            if gid in done:
                skipped += 1
                continue
            f = tf.extractfile(info)
            if not f:
                continue
            try:
                text = f.read().decode("utf-8", errors="replace")
            except Exception:
                continue
            n, words, chars, heading = summarise(text)
            if not n:
                continue
            rows.append((gid, n, words, chars, heading, now))
            books += 1
            if len(rows) >= 500:
                con.executemany(
                    "INSERT OR REPLACE INTO book_passages VALUES (?,?,?,?,?,?)",
                    rows,
                )
                con.commit()
                print(f"  {books} books", flush=True)
                rows = []
            if limit and books >= limit:
                break

    if rows:
        con.executemany(
            "INSERT OR REPLACE INTO book_passages VALUES (?,?,?,?,?,?)", rows
        )
        con.commit()

    total = con.execute("SELECT COUNT(*) FROM book_passages").fetchone()[0]
    agg = con.execute(
        "SELECT SUM(passage_count), SUM(word_count) FROM book_passages"
    ).fetchone()
    con.close()
    return {
        "books_this_run": books, "already_present": skipped,
        "books_total": total,
        "passages_represented": agg[0], "words_total": agg[1],
        "db_bytes": os.path.getsize(db_path),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tar", required=True)
    ap.add_argument("--db", default="passage_summary.sqlite")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    t = time.time()
    s = build(a.tar, a.db, a.limit)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
