#!/usr/bin/env python3
"""Split books into addressable passages — the unit questions actually want.

Every stated use case needs a paragraph, not a book: "what did Plato argue about
justice", "what does this book say about organisational scaling". Fetching 448 KB
of The Republic to answer a question about justice is the wrong granularity, and
it is the granularity everything upstream of this currently offers.

So this indexes passages the same way the payload indexes books: by byte offset
into the source text. A passage is not stored -- it is LOCATED. That matters for
three reasons:

  * Storage stays flat. 79,071 books yield millions of paragraphs; storing their
    text would multiply the corpus. Storing (gid, start, end) does not.
  * Provenance stays exact. A passage is a byte range in an immutable source with
    a known SHA-256, so any claim built on it is checkable against the original
    rather than against our copy of it.
  * The same range mechanism already works. A client fetches 2 KB instead of
    448 KB from the same asset, with no new machinery.

WHAT COUNTS AS A PASSAGE
Paragraph blocks, merged until they clear a minimum length. Gutenberg wraps hard
at ~70 columns, so a "line" is meaningless; a blank-line-delimited block is the
real semantic unit. Blocks under the floor are merged forward rather than
dropped, because a short paragraph followed by a long one is usually one thought.

WHAT IS DELIBERATELY EXCLUDED
Gutenberg wraps every book in a licence header and footer, bounded by
`*** START OF THE PROJECT GUTENBERG EBOOK ***` and `*** END OF ... ***`. That is
boilerplate, identical across 79,071 books, and indexing it would produce tens of
thousands of identical "passages" about redistribution terms. The markers are
located and everything outside them is skipped -- verified present in real files
at offsets 943 and 420370 of Frankenstein.

Chapter headings are captured as passage context rather than as passages, so a
retrieved paragraph knows where in the book it sits.

Usage:
  build_passages.py --text 84.txt --gid 84 --db passages.sqlite
  build_passages.py --tar txt-files.tar --db passages.sqlite --limit 100
"""
import argparse
import io
import json
import os
import re
import sqlite3
import sys
import tarfile
import time

MIN_CHARS = 320    # below this a block is usually a fragment, not a thought
MAX_CHARS = 2400   # above this, split -- an agent's context is not free

START = re.compile(r"\*\*\*\s*START OF TH[EIS]+ PROJECT GUTENBERG[^*]*\*\*\*",
                   re.IGNORECASE)
END = re.compile(r"\*\*\*\s*END OF TH[EIS]+ PROJECT GUTENBERG[^*]*\*\*\*",
                 re.IGNORECASE)
HEADING = re.compile(
    r"^\s*(chapter|letter|book|part|canto|act|scene|section)\s+"
    r"([ivxlcdm]+|\d+)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)
GID_RE = re.compile(r"(?:^|/)(?:pg)?(\d+)(?:-\d+)?\.txt$", re.IGNORECASE)

SCHEMA = """
CREATE TABLE IF NOT EXISTS passage (
  gid        INTEGER NOT NULL,
  seq        INTEGER NOT NULL,   -- ordinal within the book
  start      INTEGER NOT NULL,   -- byte offset into the RAW book text
  end        INTEGER NOT NULL,
  chars      INTEGER NOT NULL,
  words      INTEGER NOT NULL,
  heading    TEXT,               -- nearest preceding chapter/letter heading
  preview    TEXT,               -- first ~160 chars, for ranking without a fetch
  PRIMARY KEY (gid, seq)
);
CREATE INDEX IF NOT EXISTS ix_passage_gid ON passage(gid);

-- FTS over previews only, NOT full text. Full-text FTS over 79k books would be
-- tens of gigabytes and duplicate the corpus; previews give enough signal to
-- rank candidates, and the winning passage is then fetched by range.
--
-- content='passage' makes this an EXTERNAL-CONTENT index: FTS5 stores only the
-- inverted index and reads the text back from `passage` when it needs it.
--
-- The first build did not do this, and it cost 5.9 GB. Measured on the real run:
-- 41,501,325 rows x ~152 chars of preview, stored once in `passage` and AGAIN in
-- FTS5's internal content table -- a 22.6 GB database where roughly a quarter was
-- a verbatim second copy of text already present a few pages away.
--
-- The tradeoff is that external-content FTS does not self-maintain: rows must be
-- inserted with a matching rowid and deletes need an explicit 'delete' command.
-- Since this index is rebuilt from source rather than edited in place, that costs
-- nothing here.
CREATE VIRTUAL TABLE IF NOT EXISTS passage_search USING fts5(
  heading, preview,
  content = 'passage',
  content_rowid = 'rowid',
  tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS book_body (
  gid        INTEGER PRIMARY KEY,
  body_start INTEGER NOT NULL,   -- where the actual work begins
  body_end   INTEGER NOT NULL,   -- where the licence footer starts
  passages   INTEGER NOT NULL,
  built_at   TEXT NOT NULL
);
"""


def body_bounds(text):
    """Strip Gutenberg's licence wrapper. Returns (start, end) into text."""
    s = START.search(text)
    e = END.search(text)
    start = s.end() if s else 0
    end = e.start() if e else len(text)
    if end <= start:                      # malformed markers -- take the whole file
        return 0, len(text)
    return start, end


def split_passages(text, start, end):
    """Blank-line blocks, merged to MIN_CHARS, split at MAX_CHARS."""
    out = []
    pos = start
    buf_start = None
    buf = []

    # Gutenberg files are CRLF. Matching only "\n[ \t]*\n" finds nothing in
    # "\r\n\r\n", which silently yields ZERO passages for every book -- an empty
    # index that looks like a successful run. Caught on the first real file
    # after a single-file test on an LF copy passed.
    for m in re.finditer(r"\r?\n[ \t]*\r?\n", text[start:end]):
        abs_end = start + m.start()
        block = text[pos:abs_end]
        if block.strip():
            if buf_start is None:
                buf_start = pos
            buf.append(block)
            joined_len = abs_end - buf_start
            if joined_len >= MIN_CHARS:
                out.append((buf_start, abs_end))
                buf_start, buf = None, []
        pos = start + m.end()

    if buf_start is not None and pos > buf_start:
        out.append((buf_start, min(pos, end)))

    # Split anything oversized on sentence boundaries where possible.
    final = []
    for a, b in out:
        while b - a > MAX_CHARS:
            window = text[a + MIN_CHARS:a + MAX_CHARS]
            cut = window.rfind(". ")
            split_at = a + MIN_CHARS + cut + 1 if cut > 0 else a + MAX_CHARS
            final.append((a, split_at))
            a = split_at
        if b > a:
            final.append((a, b))
    return final


def headings_index(text, start, end):
    return [(m.start() + start, m.group(0).strip()[:80])
            for m in HEADING.finditer(text[start:end])]


def heading_for(pos, heads):
    best = None
    for off, h in heads:
        if off <= pos:
            best = h
        else:
            break
    return best


def index_book(con, gid, text, now):
    start, end = body_bounds(text)
    heads = headings_index(text, start, end)
    spans = split_passages(text, start, end)

    rows, fts = [], []
    for i, (a, b) in enumerate(spans):
        chunk = text[a:b].strip()
        if not chunk:
            continue
        preview = " ".join(chunk[:160].split())
        h = heading_for(a, heads)
        rows.append((gid, i, a, b, b - a, len(chunk.split()), h, preview))
        fts.append((gid, i, h or "", preview))

    con.executemany(
        "INSERT OR REPLACE INTO passage VALUES (?,?,?,?,?,?,?,?)", rows
    )
    # External-content FTS: index by the rowid the base table just assigned, so
    # FTS5 reads the text back from `passage` rather than storing a second copy.
    con.execute(
        """INSERT INTO passage_search (rowid, heading, preview)
           SELECT rowid, COALESCE(heading,''), preview FROM passage WHERE gid = ?""",
        (gid,),
    )
    con.execute(
        "INSERT OR REPLACE INTO book_body VALUES (?,?,?,?,?)",
        (gid, start, end, len(rows), now),
    )
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--text", help="single plaintext book")
    ap.add_argument("--gid", type=int)
    ap.add_argument("--tar", help="tar of many books")
    ap.add_argument("--db", default="passages.sqlite")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    con = sqlite3.connect(a.db)
    con.executescript(SCHEMA)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    t0 = time.time()
    books = passages = 0

    if a.text:
        txt = open(a.text, encoding="utf-8", errors="replace").read()
        passages += index_book(con, a.gid or 0, txt, now)
        books = 1
    elif a.tar:
        with tarfile.open(a.tar, "r|*") as tf:
            for info in tf:
                if not info.isfile():
                    continue
                m = GID_RE.search(info.name)
                if not m:
                    continue
                f = tf.extractfile(info)
                if f is None:
                    continue
                raw = f.read()
                if info.name.endswith(".gz"):
                    import gzip
                    raw = gzip.decompress(raw)
                passages += index_book(
                    con, int(m.group(1)),
                    raw.decode("utf-8", errors="replace"), now
                )
                books += 1
                if books % 500 == 0:
                    con.commit()
                    print(f"  {books} books, {passages} passages",
                          file=sys.stderr)
                if a.limit and books >= a.limit:
                    break
    else:
        ap.print_help()
        return 2

    con.commit()
    total = con.execute("SELECT COUNT(*) FROM passage").fetchone()[0]
    con.close()
    print(json.dumps({
        "books": books,
        "passages_this_run": passages,
        "passages_total": total,
        "db": a.db,
        "elapsed_s": round(time.time() - t0, 2),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
