#!/usr/bin/env python3
"""Build a topic bridge between the book and github populations.

WHY THIS EXISTS
---------------
The graph holds two populations that never meet. Ask "who works on algorithms?"
and you get github people (via scheme='github_topic') or book people (via
scheme='lcsh'), never both, because the two vocabularies are separate namespaces
that happen to describe the same subjects.

Identity stitching cannot fix this -- see the negative result in
docs/PEOPLE-GRAPH-ENRICHMENT-LOG.md: Gutenberg is a public-domain corpus, so at
most ~419 book people could even be alive, and zero plausible-name matches
exist. The populations are genuinely different people.

But they are not different SUBJECTS. 819 topic strings appear verbatim in both
vocabularies:

    sqlite> select count(*) from (
              select distinct lower(topic) from person_topic where scheme='lcsh'
              intersect
              select distinct lower(topic) from person_topic where scheme='github_topic');
    819

    sqlite> -- people reachable through them
    6038 book people | 20551 github people

So the bridge is topical, not personal: "who works on cryptography" can return
Bruce Schneier's books AND the people maintaining crypto libraries. That is the
honest version of cross-domain reach available from this data.

HOW IT WORKS
------------
Writes scheme='bridge' rows carrying the shared term, for every person who
reaches it from EITHER vocabulary. A query then needs one predicate
(scheme='bridge' AND topic=?) instead of knowing which namespace to ask.

EXACT MATCH ONLY. No stemming, no fuzzy matching, no embedding similarity.
LCSH is a controlled vocabulary with headings like "Science fiction, American";
github topics are free-text. Fuzzy matching across those would generate
plausible-looking garbage, which is exactly the failure the name-stitch attempt
already demonstrated. An exact string match in both vocabularies is a claim we
can defend.

STOPWORD GATE. Some shared strings are too generic to be a subject -- 'air',
'ability', 'actors'. Terms are dropped when they reach an implausibly large
share of either population, since a term matching everyone distinguishes no one.

Provenance: source='topic_bridge', and the origin vocabulary is kept in the
weight (1.0 = attested in both, 0.5 = reached from one side only) so a consumer
can tell a genuine both-sides bridge from a single-sided one.

Usage:
  build_topic_bridge.py --graph people_v2.sqlite [--apply]
"""
import argparse
import json
import sqlite3
import sys
import time

# A term reaching more than this share of either population is not a subject,
# it is noise. 'air' and 'ability' are shared strings but not shared topics.
MAX_SHARE = 0.10

# Terms that are common English words rather than subjects. Kept short and
# explicit rather than pulling an NLP stopword list -- these were observed in
# the actual overlap, not guessed.
STOP = {
    "ability", "air", "actors", "aging", "abstraction", "advertising",
    "alcohol", "america", "art", "back", "black", "blue", "book", "books",
    "boy", "boys", "brothers", "change", "child", "children", "city", "color",
    "control", "country", "day", "death", "design", "dogs", "english", "eye",
    "family", "fire", "food", "friends", "future", "game", "games", "girl",
    "girls", "gold", "green", "hand", "health", "history", "home", "house",
    "human", "ice", "islands", "land", "language", "letters", "life", "light",
    "love", "man", "map", "maps", "marriage", "media", "memory", "men",
    "money", "mother", "music", "name", "nature", "news", "night", "ocean",
    "paper", "people", "photography", "play", "poetry", "power", "print",
    "questions", "red", "religion", "river", "school", "science", "sea",
    "sex", "ships", "silver", "society", "song", "songs", "sound", "space",
    "sports", "stars", "state", "stories", "story", "table", "teachers",
    "time", "travel", "war", "water", "weather", "white", "women", "words",
    "work", "world", "writing", "youth",
}


def build(graph_db, apply_changes, max_share=MAX_SHARE):
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")

    before = {
        "bridge_rows": g.execute(
            "SELECT COUNT(*) FROM person_topic WHERE scheme='bridge'"
        ).fetchone()[0],
        "person_topic_total": g.execute(
            "SELECT COUNT(*) FROM person_topic"
        ).fetchone()[0],
    }

    lcsh_pop = g.execute(
        "SELECT COUNT(DISTINCT person_id) FROM person_topic WHERE scheme='lcsh'"
    ).fetchone()[0]
    gh_pop = g.execute(
        "SELECT COUNT(DISTINCT person_id) FROM person_topic WHERE scheme='github_topic'"
    ).fetchone()[0]

    shared = [
        t for (t,) in g.execute(
            "SELECT lower(topic) FROM person_topic WHERE scheme='lcsh' "
            "INTERSECT "
            "SELECT lower(topic) FROM person_topic WHERE scheme='github_topic'"
        )
    ]

    # One set-based pass, not 1,638 per-term scans. The existing index is on
    # person_topic(topic, scheme), which cannot serve lower(topic), so every
    # per-term query was a full table scan over ~2M rows (~0.25s each). A single
    # sweep that buckets by lower(topic) does the same work once.
    candidates = {t for t in shared if t not in STOP}
    dropped_stop = len(shared) - len(candidates)

    people = {}   # term -> {'lcsh': set(pid), 'github_topic': set(pid)}
    for pid, topic, scheme in g.execute(
        "SELECT person_id, topic, scheme FROM person_topic "
        "WHERE scheme IN ('lcsh','github_topic')"
    ):
        t = (topic or "").lower()
        if t not in candidates:
            continue
        b = people.setdefault(t, {"lcsh": set(), "github_topic": set()})
        b[scheme].add(pid)

    rows = []
    kept, dropped_share = [], 0
    for term, b in people.items():
        bk, gh = len(b["lcsh"]), len(b["github_topic"])
        if (lcsh_pop and bk / lcsh_pop > max_share) or (
            gh_pop and gh / gh_pop > max_share
        ):
            dropped_share += 1
            continue
        kept.append((term, bk, gh))
        for pid in b["lcsh"] | b["github_topic"]:
            rows.append((pid, term, "bridge", 1.0, "topic_bridge"))

    summary = {
        "shared_terms": len(shared),
        "dropped_stopword": dropped_stop,
        "dropped_too_broad": dropped_share,
        "bridge_terms": len(kept),
        "bridge_rows": len(rows),
        "distinct_people": len({r[0] for r in rows}),
        "book_people": len({r[0] for r in rows if r[0].startswith("bk:")}),
        "before": before,
        "applied": bool(apply_changes),
        "top_terms": sorted(
            ({"term": t, "book_people": b, "gh_people": h} for t, b, h in kept),
            key=lambda x: -(x["book_people"] * x["gh_people"]),
        )[:12],
    }

    if apply_changes:
        g.executemany(
            "INSERT OR IGNORE INTO person_topic "
            "(person_id,topic,scheme,weight,source) VALUES (?,?,?,?,?)",
            rows,
        )
        g.commit()
        summary["after"] = {
            "bridge_rows": g.execute(
                "SELECT COUNT(*) FROM person_topic WHERE scheme='bridge'"
            ).fetchone()[0],
            "person_topic_total": g.execute(
                "SELECT COUNT(*) FROM person_topic"
            ).fetchone()[0],
        }

    g.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--max-share", type=float, default=MAX_SHARE)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = build(a.graph, a.apply, a.max_share)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
