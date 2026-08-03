#!/usr/bin/env python3
"""Build the v2 people graph from domain sources.

v2 is a REBUILD, not an in-place migration. Every loader is deterministic, so
regenerating from source is cheaper and safer than altering a live database --
and it avoids the exact bug this script exists because of: migrating v1 -> v2
by reading v1 silently dropped 27,771 life dates, because v1 never had
birth_year/death_year columns. Source is the only safe input.

Inputs (all read-only):
  --v1      existing canonical graph: github/youtube/registry people + edges
  --people  books people graph (build_people_graph.py output)
  --books   books catalog (build_books_module.py output)

Output: a v2 database with life dates, joinable topics, FTS name search, and
identity claims ready to be populated by a matcher.

Usage:
  build_people_graph_v2.py --v1 people.sqlite --people bkpeople.sqlite \
      --books books.sqlite --out people_v2.sqlite
"""
import argparse
import json
import os
import sqlite3
import sys
import time

SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "people_schema_v2.sql")


def build(v1_db, people_db, books_db, out_db):
    if os.path.exists(out_db):
        os.remove(out_db)

    g = sqlite3.connect(out_db)
    g.executescript(open(SCHEMA).read())
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    g.execute(f"ATTACH DATABASE 'file:{v1_db}?mode=ro' AS v1", ())
    g.execute(f"ATTACH DATABASE 'file:{people_db}?mode=ro' AS bkp", ())
    g.execute(f"ATTACH DATABASE 'file:{books_db}?mode=ro' AS bk", ())

    # 1. People already in the canonical graph (github / youtube / registry).
    g.execute(
        """INSERT OR IGNORE INTO person
           (person_id,name,kind,state,origin,primary_tier,rank_score,built_at)
           SELECT person_id,name,'human','linked',origin,primary_tier,
                  rank_score,? FROM v1.person""",
        (now,),
    )

    # 2. Book people, matched against the canonical graph by normalised name so
    #    someone already known from github/youtube keeps their id and gains book
    #    edges rather than being duplicated. Corporate "authors" (870 of them --
    #    "United States", "Various") are excluded: they are real catalog entries
    #    but not people, and conflating them corrupts any question of the form
    #    "what does this person believe".
    existing = {}
    for pid, name in g.execute("SELECT person_id, name FROM person"):
        existing.setdefault(" ".join((name or "").split()).lower(), pid)

    id_for_key = {}
    for pk, dn, b, d, works in g.execute(
        """SELECT person_key,display_name,birth_year,death_year,work_count
           FROM bkp.person WHERE is_corporate = 0"""
    ).fetchall():
        nkey = " ".join((dn or "").split()).lower()
        if nkey in existing:
            id_for_key[pk] = existing[nkey]
            continue
        pid = f"bk:{pk}"
        g.execute(
            """INSERT OR IGNORE INTO person
               (person_id,name,sort_name,kind,state,origin,rank_score,
                birth_year,death_year,built_at)
               VALUES (?,?,?,'human','linked','books',?,?,?,?)""",
            (pid, dn, dn, float(works), b, d, now),
        )
        existing[nkey] = pid
        id_for_key[pk] = pid

    # Life dates for people who were ALREADY in the graph (Plato, Aristotle and
    # Confucius are registry entries; books is what knows when they lived).
    for pk, b, d in g.execute(
        """SELECT person_key,birth_year,death_year FROM bkp.person
           WHERE is_corporate = 0 AND birth_year IS NOT NULL"""
    ).fetchall():
        pid = id_for_key.get(pk)
        if pid:
            g.execute(
                "UPDATE person SET birth_year=?, death_year=? "
                "WHERE person_id=? AND birth_year IS NULL",
                (b, d, pid),
            )

    # Book authorship edges. Role lives on the edge, so a translator and an
    # author of the same work are two distinct rows.
    for pk, gid, role in g.execute(
        "SELECT person_key,gid,role FROM bkp.person_work"
    ).fetchall():
        pid = id_for_key.get(pk)
        if not pid:
            continue
        title = g.execute(
            "SELECT title FROM bk.book WHERE gid=?", (gid,)
        ).fetchone()
        g.execute(
            """INSERT OR IGNORE INTO person_content
               (person_id,domain,content_ref,role,title,source,observed_at)
               VALUES (?,'book',?,?,?,'gutenberg',?)""",
            (pid, str(gid), role, title[0] if title else None, now),
        )

    # 3. Content edges, now carrying provenance so a bad loader's output is
    #    identifiable and removable as a set.
    g.execute(
        """INSERT OR IGNORE INTO person_content
           (person_id,domain,content_ref,role,score,title,source,observed_at,
            meta_json)
           SELECT person_id,domain,content_ref,'author',score,title,
                  'v1_migration',?,meta_json FROM v1.person_content""",
        (now,),
    )
    g.execute(
        """INSERT OR IGNORE INTO external_ids
           (person_id,platform,value,confidence,source)
           SELECT person_id,platform,value,1.0,'v1_migration'
           FROM v1.external_ids"""
    )

    # 4. "Tracked" = we care about this person but nothing is linked yet.
    #    v1 could not express this, so ~9,400 registry people looked broken.
    g.execute(
        """UPDATE person SET state='tracked'
           WHERE person_id NOT IN (SELECT DISTINCT person_id FROM person_content)"""
    )

    # 5. Topics as joinable edges, derived from librarian-assigned LCSH subjects
    #    on the works a person actually produced. Replaces v1's free-text
    #    topics_json, which could not answer "who else wrote about this".
    g.execute(
        """INSERT OR IGNORE INTO person_topic
           (person_id,topic,scheme,weight,source)
           SELECT pc.person_id, s.subject, 'lcsh', COUNT(*), 'gutenberg'
           FROM person_content pc
           JOIN bk.book_subject s ON s.gid = CAST(pc.content_ref AS INTEGER)
           WHERE pc.domain='book'
           GROUP BY pc.person_id, s.subject"""
    )

    # 6. FTS over names. LIKE '%name%' is a full scan: measured 54.5ms at 36k
    #    people and linear from there, on the single most common entry point
    #    into the graph.
    g.execute(
        "INSERT INTO person_search (person_id,name,aliases) "
        "SELECT person_id,name,'' FROM person"
    )

    g.commit()

    summary = {
        "person": g.execute("SELECT COUNT(*) FROM person").fetchone()[0],
        "with_life_dates": g.execute(
            "SELECT COUNT(*) FROM person WHERE birth_year IS NOT NULL"
        ).fetchone()[0],
        "person_content": g.execute(
            "SELECT COUNT(*) FROM person_content"
        ).fetchone()[0],
        "person_topic": g.execute(
            "SELECT COUNT(*) FROM person_topic"
        ).fetchone()[0],
        "external_ids": g.execute(
            "SELECT COUNT(*) FROM external_ids"
        ).fetchone()[0],
        "states": dict(
            g.execute("SELECT state,COUNT(*) FROM person GROUP BY 1").fetchall()
        ),
        "multi_domain": g.execute(
            "SELECT COUNT(*) FROM v_person_layers WHERE domain_count >= 2"
        ).fetchone()[0],
        "out": out_db,
    }
    g.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--v1", required=True)
    ap.add_argument("--people", required=True)
    ap.add_argument("--books", required=True)
    ap.add_argument("--out", default="people_v2.sqlite")
    a = ap.parse_args()
    t = time.time()
    s = build(a.v1, a.people, a.books, a.out)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
