#!/usr/bin/env python3
"""Load curated-list validation into the people graph.

The problem this fixes: GitHub people are currently ranked by stars, which
measures popularity and age. A 2015 tutorial repo outranks a 2024 compiler.
Stars are also trivially inflatable and say nothing about whether the work is
worth reading.

Curated-list inclusion is a different and better signal. Someone READ the repo
and decided it belonged on a list. And multi-list inclusion is *independent*
editorial judgement: 84 separate maintainers each concluded `vinta/awesome-python`
was worth citing, without coordinating.

Source: pipelines/github/awesome/catalog_full.sqlite — 319,511 entries across
1,716 curated lists covering 191,586 repos, with an owner_signal rollup of
145,049 owners carrying (n_repos, n_lists, n_entries, max_repo_lists).

Two things land in the graph:

  * person_topic rows under scheme='curated_validation', so the signal is
    queryable alongside github_topic and lcsh rather than hidden in a score.
  * a peer_validation external_id recording the strongest single result — the
    highest number of independent lists citing any one of their repos.

Why not just overwrite rank_score: the graph deliberately stores no derived
verdicts. A sibling system stored tier alongside score and drifted to a 96.6%
contradiction rate. Signals go in as evidence; ranking is computed at read time
from whichever signals a question cares about.

Usage:
  load_curated_signal.py --catalog catalog_full.sqlite --graph people_v2.sqlite --apply
"""
import argparse
import json
import sqlite3
import sys
import time

# An owner cited by a single list is noise -- self-listing and vanity entries are
# common. Two independent lists is the floor where the signal means something.
MIN_LISTS = 2


def load(catalog_db, graph_db, min_lists, apply_changes):
    cat = sqlite3.connect(f"file:{catalog_db}?mode=ro", uri=True)
    g = sqlite3.connect(graph_db)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Only owners already in the graph. This loader adds SIGNAL to known people;
    # it is not a discovery pass, and inventing people from a list would bypass
    # the "produced something" membership rule.
    known = {}
    for pid, in g.execute("SELECT person_id FROM person WHERE person_id LIKE 'gh:%'"):
        known[pid[3:].lower()] = pid

    topics, extids, ranked = [], [], []
    matched = skipped = 0

    for owner, n_repos, n_lists, n_entries, max_repo_lists in cat.execute(
        """SELECT owner, n_repos, n_lists, n_entries, max_repo_lists
           FROM owner_signal WHERE n_lists >= ?""",
        (min_lists,),
    ):
        pid = known.get((owner or "").lower())
        if not pid:
            skipped += 1
            continue
        matched += 1

        # Weight is the count of distinct curated lists citing this owner's work.
        topics.append(
            (pid, "curated-list-cited", "curated_validation",
             float(n_lists), "awesome_catalog")
        )
        if max_repo_lists and max_repo_lists >= min_lists:
            topics.append(
                (pid, "peer-validated-repo", "curated_validation",
                 float(max_repo_lists), "awesome_catalog")
            )
        extids.append(
            (pid, "peer_validation", str(max_repo_lists or n_lists),
             0.9, "awesome_catalog")
        )
        ranked.append((owner, n_lists, max_repo_lists))

    summary = {
        "owner_signal_rows": matched + skipped,
        "matched_in_graph": matched,
        "not_in_graph": skipped,
        "topic_rows": len(topics),
        "min_lists": min_lists,
        "applied": bool(apply_changes),
    }

    if apply_changes:
        before = g.execute("SELECT COUNT(*) FROM person_topic").fetchone()[0]
        g.executemany(
            "INSERT OR IGNORE INTO person_topic "
            "(person_id,topic,scheme,weight,source) VALUES (?,?,?,?,?)",
            topics,
        )
        g.executemany(
            "INSERT OR IGNORE INTO external_ids "
            "(person_id,platform,value,confidence,source) VALUES (?,?,?,?,?)",
            extids,
        )
        g.commit()
        summary["person_topic_before"] = before
        summary["person_topic_after"] = g.execute(
            "SELECT COUNT(*) FROM person_topic"
        ).fetchone()[0]

    summary["top_by_independent_lists"] = [
        {"owner": o, "lists": l, "best_repo_lists": m}
        for o, l, m in sorted(ranked, key=lambda x: -(x[2] or 0))[:10]
    ]

    g.close()
    cat.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--min-lists", type=int, default=MIN_LISTS)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = load(a.catalog, a.graph, a.min_lists, a.apply)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
