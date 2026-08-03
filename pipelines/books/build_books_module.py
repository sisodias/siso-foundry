#!/usr/bin/env python3
"""Build the books metadata module from the Project Gutenberg bulk catalog.

Design notes (why it looks like this):
  * Membership is a RELATION, not a path. Measured on real data, ~100% of books
    carry multiple subjects, so filing each book under one folder would discard
    most of what the catalog already knows. book_subject/book_shelf are edge
    tables; a book appears on every shelf it belongs to.
  * Section/bookcase come from LoCC (Library of Congress Classification), which
    the catalog supplies for 99.98% of texts. We inherit a century-old taxonomy
    instead of inventing or LLM-guessing one.
  * Nothing stores a derived verdict. No score, no tier. Those are projections
    computed from evidence at read time -- storing them is what let the existing
    library drift to 96.6% tier/score disagreement.

Source: https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv (~21MB, daily)
Usage:  build_books_module.py --csv pg_catalog.csv --db books.sqlite
"""
import argparse
import csv
import json
import re
import sqlite3
import sys
import time

# LoC top-level letter -> section name. Source: Library of Congress
# Classification outline. Only letters present in the PG catalog are needed,
# but the full set is cheap and avoids an "unknown" bucket appearing later.
LOC_SECTIONS = {
    "A": "General Works",
    "B": "Philosophy, Psychology, Religion",
    "C": "Auxiliary Sciences of History",
    "D": "World History",
    "E": "History of the Americas",
    "F": "Local History of the Americas",
    "G": "Geography, Anthropology, Recreation",
    "H": "Social Sciences",
    "J": "Political Science",
    "K": "Law",
    "L": "Education",
    "M": "Music",
    "N": "Fine Arts",
    "P": "Language and Literature",
    "Q": "Science",
    "R": "Medicine",
    "S": "Agriculture",
    "T": "Technology",
    "U": "Military Science",
    "V": "Naval Science",
    "Z": "Bibliography, Library Science",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS book (
  gid           INTEGER PRIMARY KEY,     -- Gutenberg Text#, the stable id
  title         TEXT NOT NULL,
  authors       TEXT,                    -- raw catalog string
  language      TEXT,
  issued        TEXT,                    -- PG release date, NOT print date
  media_type    TEXT,
  text_url      TEXT,
  rights        TEXT NOT NULL,           -- never inferred; see --rights
  source        TEXT NOT NULL,
  fetched_at    TEXT NOT NULL,
  raw           TEXT NOT NULL            -- the ENTIRE source row, verbatim JSON
);

-- Lossless column capture. The parsed tables above are a convenience view over
-- upstream metadata; this is the archival copy. Every column the catalog ships
-- is preserved per book, including columns added upstream after we wrote this
-- -- the loader never drops a field it does not recognise. If our parsing is
-- ever wrong, the truth is still here and the module can be rebuilt without
-- re-fetching. Non-Text media (Sound/Dataset/Image) is retained too, since
-- discarding rows is also metadata loss.
CREATE TABLE IF NOT EXISTS book_field (
  gid INTEGER NOT NULL, field TEXT NOT NULL, value TEXT,
  PRIMARY KEY (gid, field)
);
CREATE INDEX IF NOT EXISTS ix_field ON book_field(field);

-- Edge tables. A book belongs to as many subjects/shelves/classes as the
-- catalog says it does. Adding a membership is an INSERT, never a move.
CREATE TABLE IF NOT EXISTS book_subject (
  gid INTEGER NOT NULL, subject TEXT NOT NULL,
  PRIMARY KEY (gid, subject)
);
CREATE TABLE IF NOT EXISTS book_shelf (
  gid INTEGER NOT NULL, shelf TEXT NOT NULL,
  PRIMARY KEY (gid, shelf)
);
CREATE TABLE IF NOT EXISTS book_class (
  gid INTEGER NOT NULL,
  locc TEXT NOT NULL,                    -- full code, e.g. "PR"
  section TEXT NOT NULL,                 -- top letter, e.g. "P"
  bookcase TEXT NOT NULL,                -- two-letter, e.g. "PR"
  PRIMARY KEY (gid, locc)
);

-- Facets: LCSH headings are hierarchical, split on " -- ".
-- "Private investigators -- England -- Fiction" -> 3 facets at depths 0,1,2.
CREATE TABLE IF NOT EXISTS subject_facet (
  subject TEXT NOT NULL, facet TEXT NOT NULL, depth INTEGER NOT NULL,
  PRIMARY KEY (subject, depth)
);

CREATE INDEX IF NOT EXISTS ix_subject   ON book_subject(subject);
CREATE INDEX IF NOT EXISTS ix_shelf     ON book_shelf(shelf);
CREATE INDEX IF NOT EXISTS ix_section   ON book_class(section);
CREATE INDEX IF NOT EXISTS ix_bookcase  ON book_class(bookcase);
CREATE INDEX IF NOT EXISTS ix_facet     ON subject_facet(facet);
CREATE INDEX IF NOT EXISTS ix_lang      ON book(language);
"""


def split_multi(value):
    """Catalog packs repeated values into one cell, separated by ';'."""
    if not value:
        return []
    return [p.strip() for p in value.split(";") if p.strip()]


def parse_locc(code):
    """'PR' -> ('P', 'PR'). 'D501' -> ('D', 'D5'). Returns None if unusable."""
    code = (code or "").strip().upper()
    m = re.match(r"^([A-Z])([A-Z]?)", code)
    if not m or m.group(1) not in LOC_SECTIONS:
        return None
    section = m.group(1)
    bookcase = section + m.group(2) if m.group(2) else section
    return section, bookcase


def build(csv_path, db_path, rights, source_label):
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    books = subjects = shelves = classes = 0
    skipped_nontext = 0
    facets = {}

    with open(csv_path, encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            try:
                gid = int((row.get("Text#") or "").strip())
            except ValueError:
                continue

            media = (row.get("Type") or "").strip()
            # Retain every row. Non-Text media is still catalog metadata and
            # discarding it would be exactly the loss we are trying to avoid;
            # callers filter on media_type when they want books only.
            if media != "Text":
                skipped_nontext += 1

            # Archival copy: the whole row, every column, unmodified.
            for field, value in row.items():
                if field is None:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO book_field VALUES (?,?,?)",
                    (gid, field, value),
                )

            conn.execute(
                "INSERT OR REPLACE INTO book VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    gid,
                    (row.get("Title") or "").strip(),
                    (row.get("Authors") or "").strip(),
                    (row.get("Language") or "").strip(),
                    (row.get("Issued") or "").strip(),
                    media,
                    f"https://www.gutenberg.org/ebooks/{gid}.txt.utf-8"
                    if media == "Text"
                    else None,
                    rights,
                    source_label,
                    now,
                    json.dumps(row, ensure_ascii=False),
                ),
            )
            books += 1

            for subj in split_multi(row.get("Subjects")):
                conn.execute(
                    "INSERT OR IGNORE INTO book_subject VALUES (?,?)", (gid, subj)
                )
                subjects += 1
                if subj not in facets:
                    facets[subj] = [p.strip() for p in subj.split("--") if p.strip()]

            for shelf in split_multi(row.get("Bookshelves")):
                conn.execute(
                    "INSERT OR IGNORE INTO book_shelf VALUES (?,?)", (gid, shelf)
                )
                shelves += 1

            for code in split_multi(row.get("LoCC")):
                parsed = parse_locc(code)
                if not parsed:
                    continue
                section, bookcase = parsed
                conn.execute(
                    "INSERT OR IGNORE INTO book_class VALUES (?,?,?,?)",
                    (gid, code.strip(), section, bookcase),
                )
                classes += 1

    for subj, parts in facets.items():
        for depth, facet in enumerate(parts):
            conn.execute(
                "INSERT OR IGNORE INTO subject_facet VALUES (?,?,?)",
                (subj, facet, depth),
            )

    conn.commit()
    summary = {
        "rows_loaded": books,
        "non_text_media_retained": skipped_nontext,
        "book_subject_edges": subjects,
        "book_shelf_edges": shelves,
        "book_class_edges": classes,
        "distinct_subjects": len(facets),
        "db": db_path,
    }
    conn.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default="pg_catalog.csv")
    ap.add_argument("--db", default="books.sqlite")
    ap.add_argument(
        "--rights",
        default="public_domain_us",
        help="Recorded verbatim per book. Never guessed; 'pending' is valid.",
    )
    ap.add_argument("--source", default="project_gutenberg")
    args = ap.parse_args()

    print(json.dumps(build(args.csv, args.db, args.rights, args.source), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
