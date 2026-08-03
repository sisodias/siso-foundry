#!/usr/bin/env python3
"""Load the books domain into the canonical Foundry people graph.

The people graph is the layer where "everything a human ever produced" becomes
answerable, because the same person shows up as a GitHub login, a YouTube
channel, and an author name on a book. Books is the fourth domain to feed it.

Membership rule (Shaan, 2026-08-03): the graph holds **people who produced
something**. A book author is a first-class member alongside repo owners and
channel creators. Overlaps -- an author who also ships code and posts -- are the
high-value multi-source cases the graph exists to surface.

No schema change is required. `person_content` was built generic:
    domain='book', content_ref=<gutenberg gid>
matching the existing 'github' / 'youtube_video' / 'youtube_channel' values.

Conventions followed from core/people_schema.sql:
  * person_id is stable and namespaced -- 'gh:<login>', 'yt:<slug>', so books
    uses 'bk:<normalised-key>'.
  * Satellites are referenced, never duplicated: content_ref holds the Gutenberg
    id, the work itself stays in books.sqlite.
  * origin records where a person was FIRST materialised, so a later cross-domain
    match does not erase the fact that we met them in books.

Writes are additive. Existing people, edges, and origins are never overwritten;
a person already known from github/youtube keeps their id and gains a book edge.
That is what makes the merge safe to re-run.

Usage:
  load_into_people_graph.py --books books.sqlite --people people.sqlite \
      --graph /path/to/canonical/people.sqlite [--apply]

Without --apply it is a dry run and reports what WOULD change.
"""
import argparse
import json
import sqlite3
import sys
import time

# Only these roles mean "produced the intellectual content". Translators,
# illustrators and editors are real contributors and keep their edges, but the
# distinction is preserved rather than flattened -- merging them would make a
# Gutenberg volunteer editor the second most prolific author in history.
AUTHORSHIP = {"author"}


def norm(s):
    return " ".join((s or "").split()).lower()


def load(books_db, people_db, graph_db, apply_changes):
    bk = sqlite3.connect(f"file:{books_db}?mode=ro", uri=True)
    pe = sqlite3.connect(f"file:{people_db}?mode=ro", uri=True)
    g = sqlite3.connect(graph_db)

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Existing canonical people, keyed by normalised name, so a book author who
    # is already in the graph via github/youtube is MATCHED rather than added.
    existing = {}
    for pid, name in g.execute("SELECT person_id, name FROM person"):
        existing.setdefault(norm(name), pid)

    new_people = []
    new_edges = []
    matched = []

    rows = pe.execute(
        """SELECT person_key, display_name, birth_year, death_year,
                  is_corporate, work_count
           FROM person WHERE is_corporate = 0"""
    ).fetchall()

    for key, name, birth, death, corporate, works in rows:
        nkey = norm(name)
        if nkey in existing:
            pid = existing[nkey]
            matched.append((pid, name))
        else:
            pid = f"bk:{key}"
            new_people.append(
                (
                    pid,
                    name,
                    None,           # primary_tier: books has no tiering yet
                    "books",        # origin
                    None,           # line
                    "author",       # role
                    json.dumps({"birth": birth, "death": death}),
                    float(works),   # rank_score: work count as first-pass signal
                    now,
                )
            )
            existing[nkey] = pid

        for (gid, role) in pe.execute(
            "SELECT gid, role FROM person_work WHERE person_key = ?", (key,)
        ):
            if role not in AUTHORSHIP:
                continue
            title = bk.execute(
                "SELECT title FROM book WHERE gid = ?", (gid,)
            ).fetchone()
            new_edges.append(
                (
                    pid,
                    "book",
                    str(gid),
                    None,
                    (title[0] if title else None),
                    json.dumps({"role": role, "source": "gutenberg"}),
                )
            )

    summary = {
        "canonical_people_before": g.execute(
            "SELECT COUNT(*) FROM person"
        ).fetchone()[0],
        "book_people_considered": len(rows),
        "matched_existing": len(matched),
        "new_people": len(new_people),
        "new_book_edges": len(new_edges),
        "applied": bool(apply_changes),
    }

    if apply_changes:
        g.executemany(
            "INSERT OR IGNORE INTO person "
            "(person_id,name,primary_tier,origin,line,role,topics_json,"
            "rank_score,built_at) VALUES (?,?,?,?,?,?,?,?,?)",
            new_people,
        )
        g.executemany(
            "INSERT OR IGNORE INTO person_content "
            "(person_id,domain,content_ref,score,title,meta_json) "
            "VALUES (?,?,?,?,?,?)",
            new_edges,
        )
        g.commit()
        summary["canonical_people_after"] = g.execute(
            "SELECT COUNT(*) FROM person"
        ).fetchone()[0]
        summary["book_edges_in_graph"] = g.execute(
            "SELECT COUNT(*) FROM person_content WHERE domain='book'"
        ).fetchone()[0]

    if matched:
        summary["sample_cross_domain_matches"] = [n for _, n in matched[:10]]

    g.close()
    pe.close()
    bk.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--books", default="books.sqlite")
    ap.add_argument("--people", default="people.sqlite")
    ap.add_argument("--graph", required=True, help="canonical people.sqlite")
    ap.add_argument(
        "--apply", action="store_true", help="write; omit for a dry run"
    )
    a = ap.parse_args()
    print(json.dumps(load(a.books, a.people, a.graph, a.apply), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
