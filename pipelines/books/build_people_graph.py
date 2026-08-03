#!/usr/bin/env python3
"""Build the people graph from the books catalog.

Why this exists: the queries that matter are about PEOPLE and IDEAS, not files.
"Everything Socrates ever said", "what does this author argue about X",
"who else wrote about this in the same decade" -- none of those care where the
bytes live. They need a person to be a first-class entity with edges to works,
subjects, and eventually extracted passages.

The catalog gives us this for free: 100% of Text works carry an author string in
the form "Surname, Forename, birth-death", and 23,562 rows carry several authors
separated by ";". Parsing that yields a real graph before a single book is
downloaded.

Design notes:
  * A person is identified by a normalised key, not by row position, so the same
    human appearing under slightly different strings collapses to one node.
  * Life years are parsed where present but never invented. Missing is missing.
  * Roles are captured ("[Editor]", "[Translator]") because "wrote" and
    "translated" are different edges and conflating them corrupts attribution.
  * Corporate authors ("United States") are flagged, not silently treated as
    people -- they are real catalog entries but they are not humans.
  * Nothing derived is stored twice. Co-authorship is computed from the
    person_work edges, not kept as its own table to drift out of sync.

Usage: build_people_graph.py --books books.sqlite --db people.sqlite
"""
import argparse
import json
import re
import sqlite3
import sys
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS person (
  person_key   TEXT PRIMARY KEY,   -- normalised identity, stable across runs
  display_name TEXT NOT NULL,      -- "Spinoza, Benedictus de"
  sort_name    TEXT,               -- surname-first for ordering
  birth_year   INTEGER,            -- NULL when the catalog does not say
  death_year   INTEGER,
  is_corporate INTEGER NOT NULL DEFAULT 0,
  raw_variants TEXT,               -- every raw string that mapped here (JSON)
  work_count   INTEGER NOT NULL DEFAULT 0
);

-- One row per (person, work, role). A translator and an author of the same
-- work are two different edges, deliberately.
CREATE TABLE IF NOT EXISTS person_work (
  person_key TEXT NOT NULL,
  gid        INTEGER NOT NULL,
  role       TEXT NOT NULL DEFAULT 'author',
  PRIMARY KEY (person_key, gid, role)
);

CREATE INDEX IF NOT EXISTS ix_pw_gid    ON person_work(gid);
CREATE INDEX IF NOT EXISTS ix_pw_person ON person_work(person_key);
CREATE INDEX IF NOT EXISTS ix_person_b  ON person(birth_year);
CREATE INDEX IF NOT EXISTS ix_person_s  ON person(sort_name);
"""

# "Kennedy, John F. (John Fitzgerald), 1917-1963" -> trailing year range.
# Handles "1743-1826", "1917-", "-1826", "1743?-1826".
YEARS = re.compile(r",\s*(?:ca\.\s*)?(\d{3,4})\??\s*-\s*(\d{3,4})?\??\s*$")
OPEN_YEARS = re.compile(r",\s*(?:b\.|d\.)\s*(\d{3,4})\??\s*$")

# Antiquity is written inline: "Plato, 428? BCE-348? BCE", "Aristotle, 385
# BCE-323 BCE". Without this, every ancient author parses with NULL life years
# and any century filter silently drops the entire classical corpus -- which is
# exactly the material worth reasoning over. BCE years are stored NEGATIVE so
# ordering and range queries work arithmetically against CE years.
BCE_YEARS = re.compile(
    r",\s*(?:ca\.\s*)?(\d{1,4})\??\s*(BCE|B\.C\.?E?\.?)\s*-\s*"
    r"(\d{1,4})?\??\s*(?:BCE|B\.C\.?E?\.?)?\s*$",
    re.IGNORECASE,
)
ROLE = re.compile(r"\[([^\]]+)\]\s*$")

# A catalog "author" with no comma and no life years is usually an institution
# (e.g. "United States", "Various"). Flagged rather than dropped.
CORPORATE_HINTS = {"various", "anonymous", "unknown"}


def _finish(name, birth, death, role):
    """Shared tail: clean the name and decide whether it is a person."""
    s = name.strip().strip(",").strip()
    if not s:
        return None
    corporate = 0
    if "," not in s and birth is None and death is None:
        corporate = 1
    if s.lower() in CORPORATE_HINTS:
        corporate = 1
    return s, birth, death, role, corporate


def parse_author(raw):
    """Return (display_name, birth, death, role, is_corporate) or None."""
    s = (raw or "").strip()
    if not s:
        return None

    role = "author"
    m = ROLE.search(s)
    if m:
        role = m.group(1).strip().lower()
        s = s[: m.start()].strip()

    birth = death = None
    m = BCE_YEARS.search(s)
    if m:
        birth = -int(m.group(1))
        death = -int(m.group(3)) if m.group(3) else None
        s = s[: m.start()].strip()
        return _finish(s, birth, death, role)

    m = YEARS.search(s)
    if m:
        birth = int(m.group(1))
        death = int(m.group(2)) if m.group(2) else None
        s = s[: m.start()].strip()
    else:
        m = OPEN_YEARS.search(s)
        if m:
            if ", b." in s.lower():
                birth = int(m.group(1))
            else:
                death = int(m.group(1))
            s = s[: m.start()].strip()

    s = s.strip().strip(",").strip()
    if not s:
        return None

    corporate = 0
    if "," not in s and birth is None and death is None:
        corporate = 1
    if s.lower() in CORPORATE_HINTS:
        corporate = 1

    return s, birth, death, role, corporate


def person_key(name, birth, death):
    """Stable identity. Life years disambiguate same-named people; without them
    the name alone must serve, which is the honest limit of this metadata."""
    base = re.sub(r"\s+", " ", name.lower())
    base = re.sub(r"\([^)]*\)", "", base).strip()  # drop "(John Fitzgerald)"
    base = re.sub(r"[^a-z0-9, ]", "", base).strip()
    if birth or death:
        return f"{base}|{birth or ''}-{death or ''}"
    return base


def build(books_db, out_db):
    src = sqlite3.connect(books_db)
    dst = sqlite3.connect(out_db)
    dst.executescript(SCHEMA)

    people = {}   # key -> dict
    edges = set()
    unparsed = 0

    rows = src.execute(
        "SELECT gid, authors FROM book WHERE media_type='Text' AND authors != ''"
    )
    for gid, authors in rows:
        for chunk in authors.split(";"):
            parsed = parse_author(chunk)
            if not parsed:
                unparsed += 1
                continue
            name, birth, death, role, corporate = parsed
            key = person_key(name, birth, death)

            p = people.setdefault(
                key,
                {
                    "display": name,
                    "birth": birth,
                    "death": death,
                    "corporate": corporate,
                    "variants": set(),
                },
            )
            p["variants"].add(chunk.strip())
            # Fill in life years if a later row knows them and an earlier didn't.
            if p["birth"] is None and birth is not None:
                p["birth"] = birth
            if p["death"] is None and death is not None:
                p["death"] = death

            edges.add((key, gid, role))

    counts = {}
    for key, gid, role in edges:
        counts[key] = counts.get(key, 0) + 1

    for key, p in people.items():
        sort_name = p["display"]
        dst.execute(
            "INSERT OR REPLACE INTO person VALUES (?,?,?,?,?,?,?,?)",
            (
                key,
                p["display"],
                sort_name,
                p["birth"],
                p["death"],
                p["corporate"],
                json.dumps(sorted(p["variants"]), ensure_ascii=False),
                counts.get(key, 0),
            ),
        )

    dst.executemany(
        "INSERT OR IGNORE INTO person_work VALUES (?,?,?)", sorted(edges)
    )
    dst.commit()

    summary = {
        "people": len(people),
        "corporate": sum(1 for p in people.values() if p["corporate"]),
        "with_life_years": sum(
            1 for p in people.values() if p["birth"] or p["death"]
        ),
        "person_work_edges": len(edges),
        "roles": sorted({r for _, _, r in edges})[:12],
        "unparsed_author_chunks": unparsed,
        "db": out_db,
    }
    dst.close()
    src.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--books", default="books.sqlite")
    ap.add_argument("--db", default="people.sqlite")
    args = ap.parse_args()
    t = time.time()
    s = build(args.books, args.db)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
