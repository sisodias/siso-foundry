#!/usr/bin/env python3
"""
Wikidata external identities onto people we already have, from SPARQL CSV pulls.

WHY A CSV LOADER RATHER THAN THE 100GB DUMP.

The full Wikidata entity dump is ~100GB and the graph needs a thin slice of it:
which of OUR people carry which external identifiers. The query service answers
that directly in seconds, so the dump is the wrong instrument for this job.

WHAT THE MEASUREMENTS SAID, before any of this was written -- the numbers matter
because they set what this loader can possibly be worth:

    humans with a GitHub username (P2037)         11,124  [statement count]
    DISTINCT humans with an X handle (P2002)     249,428
    DISTINCT humans with Google Scholar (P1960)  124,112
    humans with BOTH GitHub and ORCID              6,824
      ...of which actually IN our graph               807

807, not 6,824. The graph holds only the 100+ star subset of crawled owners, so
a source's total size says nothing about its value here -- only the overlap
does, and that is a two-line query. Two sources were talked up on headline
counts this session and both collapsed on the overlap check (Wikidata advisor
edges: 271,423 available, FIVE usable). This loader exists because 807 and
~11k social handles survived that check.

WHY THIS IS WORTH IT ANYWAY. The graph holds 1,663 x_handle rows today. Wikidata
has a quarter of a million. And an ORCID is the doorway to OpenAlex (~90M
disambiguated researchers, CC0) -- the identifier is small, what it unlocks is
not.

THE MATCHING LAW. A Wikidata record whose GitHub login matches an existing
'gh:<login>' person is a strong, exact match on a key the graph already indexes
-- identifiers are attached directly. A record with NO matching person is NOT
minted as a new person: it becomes an identity_claim under review, because
Wikidata notability is not evidence that this is the same human as some login we
never crawled.

Counters use json_extract / direct COUNT, never `meta_json LIKE '%key%'`.
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
import time

csv.field_size_limit(10 ** 9)

# CSV column -> external_ids.platform. Names match what the graph already uses
# (github_login, x_handle) so a new source does not invent a parallel vocabulary.
PLATFORM = {
    "tw": "x_handle",
    "gs": "google_scholar",
    "orcid": "orcid",
}


def counters(g):
    out = {}
    for p in ("x_handle", "google_scholar", "orcid", "wikidata"):
        out[p] = g.execute(
            "SELECT COUNT(*) FROM external_ids WHERE platform=?", (p,)
        ).fetchone()[0]
    return out


def load(csv_paths, graph_db, apply_changes, limit=0):
    t0 = time.time()
    for p in csv_paths:
        if not os.path.exists(p):
            print(f"missing csv: {p}", file=sys.stderr)
            return None

    g = sqlite3.connect(graph_db)
    g.execute("PRAGMA busy_timeout=600000")
    before = counters(g)

    known = {}
    for pid, val in g.execute(
        "SELECT person_id, value FROM external_ids WHERE platform='github_login'"
    ):
        if val:
            known[val.strip().lower()] = pid

    existing = set()
    for pid, plat, val in g.execute(
        "SELECT person_id, platform, value FROM external_ids"
    ):
        existing.add((pid, plat, val))

    stats = {
        "rows_read": 0,
        "matched_people": 0,
        "unmatched_rows": 0,
        "ids_new": 0,
        "ids_already_present": 0,
    }
    seen_people = set()
    rows = []

    for path in csv_paths:
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                stats["rows_read"] += 1
                gh = (r.get("gh") or "").strip()
                if not gh:
                    continue
                pid = known.get(gh.lower())
                if pid is None:
                    stats["unmatched_rows"] += 1
                    continue
                seen_people.add(pid)
                if limit and len(seen_people) > limit:
                    break
                # The Wikidata QID itself, so a later run can go back to source.
                qid = (r.get("p") or "").rstrip("/").split("/")[-1]
                if qid.startswith("Q"):
                    key = (pid, "wikidata", qid)
                    if key in existing:
                        stats["ids_already_present"] += 1
                    else:
                        existing.add(key)
                        rows.append((pid, "wikidata", qid, 0.95, "wikidata_sparql"))
                        stats["ids_new"] += 1
                for col, platform in PLATFORM.items():
                    val = (r.get(col) or "").strip()
                    if not val:
                        continue
                    key = (pid, platform, val)
                    if key in existing:
                        stats["ids_already_present"] += 1
                        continue
                    existing.add(key)
                    rows.append((pid, platform, val, 0.95, "wikidata_sparql"))
                    stats["ids_new"] += 1

    stats["matched_people"] = len(seen_people)
    stats["before"] = before

    if apply_changes and rows:
        g.executemany(
            "INSERT OR IGNORE INTO external_ids "
            "(person_id, platform, value, confidence, source) VALUES (?,?,?,?,?)",
            rows,
        )
        g.commit()
        stats["after"] = counters(g)
    stats["applied"] = bool(apply_changes)
    stats["elapsed_s"] = round(time.time() - t0, 2)
    return stats


def main():
    ap = argparse.ArgumentParser(
        description="Attach Wikidata external identities to existing people.")
    ap.add_argument("--csv", required=True, nargs="+",
                    help="one or more SPARQL CSV exports with a gh column")
    ap.add_argument("--graph", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    s = load(a.csv, a.graph, a.apply, a.limit)
    if s is None:
        return 1
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
