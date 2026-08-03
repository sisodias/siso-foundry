#!/usr/bin/env python3
"""Enrich book edges: addressable text, subjects, and work shape.

WHY THIS EXISTS
---------------
Eight rounds of enrichment went to GitHub. The books population was left with
one signal on 0.6% of its edges:

    sqlite> select count(*) total, sum(meta_json='{}') empty from person_content
            where domain='book';
    101124|100518

99.4% of book edges carry an empty meta_json while every one of 463,230 github
edges is enriched. Books hold 35,363 people -- the second-largest population in
the graph -- and almost nothing is known about any individual edge.

THREE THINGS MOVE HERE, all from data already on disk:

1. ADDRESSABLE TEXT (locator.sqlite). Distinct from the `has_text` flag written
   by load_passage_signal.py, and the distinction matters:
     - passage.gid  = text has been SEGMENTED (500 books; the builder is slow)
     - location.gid = text is ADDRESSABLE by byte range (77,540 books and rising)
   Addressable is the weaker but far broader claim, and it is the one that
   answers "can this person be read at all". Written as `text_addressable`
   alongside byte length, NOT conflated with has_text.

2. AUTHOR SUBJECTS, HONESTLY LABELLED. person_topic holds 167,585 LCSH rows for
   book people. They sit on the PERSON, and no per-book subject data exists
   anywhere in this corpus -- verified: every lcsh row is keyed by person_id
   ('aristotle' -> 'Aesthetics -- Early works to 1800'), and locator.sqlite has
   only `location` and `asset` tables.

   So this writes `author_subjects`, NOT `subjects`. The distinction is the
   whole point: an author of both a cookery book and a theology treatise gets
   both headings on both edges, and calling that field `subjects` would assert
   a per-book fact we do not have. Answering "what is THIS book about" needs
   per-gid subject data that must be harvested first; this field is the
   author-level approximation and is named so a consumer cannot mistake it.

3. WORK SHAPE. role and title already exist per edge; what is missing is the
   author's own scale -- how many works, in how many roles. Written per edge so
   a query can weight a person's 40th minor edit differently from their sole
   monograph.

WHAT THIS DOES NOT DO. It does not touch person.topics_json (empty for all
35,363 book people) -- that is a person-level rollup and a separate concern from
edge enrichment; conflating them is how the v1 graph put role on the person.

Reads locator.sqlite mode=ro. Nothing on /Volumes is written (C5).

Usage:
  load_book_edge_signal.py --locator locator.sqlite --graph people_v2.sqlite [--apply]
"""
import argparse
import json
import sqlite3
import sys
import time

COUNT_SQL = (
    "SELECT COUNT(*) FROM person_content WHERE domain='book' "
    "AND json_extract(meta_json,'$.text_addressable') IS NOT NULL"
)
EMPTY_SQL = (
    "SELECT COUNT(*) FROM person_content WHERE domain='book' AND meta_json='{}'"
)


def load(locator_db, graph_db, apply_changes):
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")

    before = {
        "book_edges_total": g.execute(
            "SELECT COUNT(*) FROM person_content WHERE domain='book'"
        ).fetchone()[0],
        "book_edges_empty_meta": g.execute(EMPTY_SQL).fetchone()[0],
        "book_edges_addressable": g.execute(COUNT_SQL).fetchone()[0],
    }

    # --- 1. addressable text, by gid ---------------------------------------
    loc = sqlite3.connect(f"file:{locator_db}?mode=ro", uri=True)
    addressable = {}
    for gid, raw_len in loc.execute(
        "SELECT gid, MAX(raw_length) FROM location GROUP BY gid"
    ):
        addressable[str(gid)] = raw_len
    loc.close()

    # --- 2. per-person subjects, to be filtered onto that person's own books -
    subjects = {}
    for pid, topic in g.execute(
        "SELECT person_id, topic FROM person_topic WHERE scheme='lcsh'"
    ):
        subjects.setdefault(pid, []).append(topic)

    # --- 3. work shape per person ------------------------------------------
    shape = {}
    for pid, works, roles in g.execute(
        "SELECT person_id, COUNT(*), COUNT(DISTINCT role) FROM person_content "
        "WHERE domain='book' GROUP BY person_id"
    ):
        shape[pid] = (works, roles)

    updates = []
    stats = {"edges": 0, "with_addressable": 0, "with_subjects": 0}
    for pid, ref, role, meta_json in g.execute(
        "SELECT person_id, content_ref, role, meta_json FROM person_content "
        "WHERE domain='book'"
    ):
        try:
            meta = json.loads(meta_json or "{}")
        except (ValueError, TypeError):
            meta = {}
        touched = False

        if ref in addressable:
            meta["text_addressable"] = 1
            if addressable[ref]:
                meta["raw_bytes"] = addressable[ref]
            stats["with_addressable"] += 1
            touched = True

        subs = subjects.get(pid)
        if subs:
            # author_subjects, not subjects -- these are the PERSON's headings,
            # identical across all their works. Cap at 12: a prolific author
            # carries hundreds and the edge only needs enough to be queryable.
            meta["author_subjects"] = sorted(set(subs))[:12]
            meta.pop("subjects", None)   # correct rows written by the first run
            stats["with_subjects"] += 1
            touched = True

        if pid in shape:
            works, roles = shape[pid]
            meta["author_works"] = works
            meta["author_roles"] = roles
            touched = True

        if not touched:
            continue
        stats["edges"] += 1
        updates.append((json.dumps(meta), pid, ref, role))

    summary = dict(stats)
    summary["before"] = before
    summary["applied"] = bool(apply_changes)

    if apply_changes:
        g.executemany(
            "UPDATE person_content SET meta_json=? "
            "WHERE person_id=? AND domain='book' AND content_ref=? AND role=?",
            updates,
        )
        g.commit()
        summary["after"] = {
            "book_edges_empty_meta": g.execute(EMPTY_SQL).fetchone()[0],
            "book_edges_addressable": g.execute(COUNT_SQL).fetchone()[0],
        }

    g.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--locator", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = load(a.locator, a.graph, a.apply)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
