#!/usr/bin/env python3
"""Mark which book edges have retrievable full text.

WHY THIS EXISTS
---------------
Every enrichment so far describes work from the OUTSIDE -- how many stars, how
highly rated, how widely depended upon, how recently touched. None of it can
answer the question a people graph most obviously ought to answer:

    "What did this person actually write?"

For the book population that is now answerable for part of the corpus.
passages.sqlite holds segmented, searchable book text:

    sqlite> select count(*), count(distinct gid) from passage;
    295646|500

and `gid` is the same namespace the graph already uses as `content_ref` for
book edges, so the join is exact -- no matching heuristics, no fuzzy names.
Measured overlap at the time of writing:

    passage_gids 500 | matching_book_edges 606 | distinct_people 442

WHAT THIS WRITES into person_content.meta_json, for book edges only:
  has_text        1 -- this work's text is retrievable
  passage_count   number of segments
  word_count      summed words across segments
  first_heading   nearest chapter/letter heading of the first segment

WHY A FLAG AND NOT THE TEXT. The text is 174 MB and lives on the vault under a
single-writer job. Copying it into the graph would duplicate a large corpus into
a file that is meant to be an index of people, and it would go stale the moment
the passage builder advances. The flag plus the counts is what makes the graph
able to ANSWER "can I read this person?" -- retrieval then goes to
passages.sqlite by gid, which is what that database is for.

DELIBERATELY RE-RUNNABLE AND EXPECTED TO GROW. Measured headroom at the time of
writing: the graph holds 72,744 distinct books, of which 51,026 have a locator
entry (i.e. their text is addressable), while `passage` covers 500. The builder
is still running, so coverage climbs on each re-run. The loader is idempotent by
value, not by "already done": re-running after the builder advances correctly
picks up the new books.

READ-ONLY AGAINST THE VAULT. passages.sqlite is opened `mode=ro` and nothing on
/Volumes is written, moved, or unmounted -- a build job owns that directory.

Usage:
  load_passage_signal.py --passages passages.sqlite --graph people_v2.sqlite [--apply]
"""
import argparse
import json
import sqlite3
import sys
import time

COUNT_SQL = (
    "SELECT COUNT(*) FROM person_content WHERE domain='book' "
    "AND json_extract(meta_json,'$.has_text') IS NOT NULL"
)


def load(passages_db, graph_db, apply_changes):
    src = sqlite3.connect(f"file:{passages_db}?mode=ro", uri=True)
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")

    before = {
        "book_edges_with_text": g.execute(COUNT_SQL).fetchone()[0],
        "book_edges_total": g.execute(
            "SELECT COUNT(*) FROM person_content WHERE domain='book'"
        ).fetchone()[0],
    }

    # One row per book: how much text, and where it starts.
    stats_by_gid = {}
    for gid, n, words, heading in src.execute(
        "SELECT gid, COUNT(*), SUM(words), MIN(heading) FROM passage GROUP BY gid"
    ):
        stats_by_gid[str(gid)] = (n, words, heading)

    existing = {}
    for pid, ref, meta in g.execute(
        "SELECT person_id, content_ref, meta_json FROM person_content "
        "WHERE domain='book'"
    ):
        existing.setdefault(ref, []).append((pid, meta))

    updates = []
    people = set()
    matched_gids = 0
    for gid, (n, words, heading) in stats_by_gid.items():
        rows = existing.get(gid)
        if not rows:
            continue
        matched_gids += 1
        for pid, meta_json in rows:
            try:
                meta = json.loads(meta_json or "{}")
            except (ValueError, TypeError):
                meta = {}
            meta["has_text"] = 1
            meta["passage_count"] = n
            if words is not None:
                meta["word_count"] = words
            if heading:
                meta["first_heading"] = heading[:120]
            people.add(pid)
            updates.append((json.dumps(meta), pid, gid))

    summary = {
        "passage_books": len(stats_by_gid),
        "matched_gids": matched_gids,
        "edges_to_update": len(updates),
        "distinct_people": len(people),
        "before": before,
        "applied": bool(apply_changes),
    }

    if apply_changes:
        g.executemany(
            "UPDATE person_content SET meta_json=? "
            "WHERE person_id=? AND domain='book' AND content_ref=?",
            updates,
        )
        g.commit()
        summary["after"] = {
            "book_edges_with_text": g.execute(COUNT_SQL).fetchone()[0],
        }

    g.close()
    src.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--passages", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = load(a.passages, a.graph, a.apply)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
