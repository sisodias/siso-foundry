#!/usr/bin/env python3
"""Load L1 domain families into the people graph as a coarse topic layer.

WHY THIS EXISTS
---------------
person_topic currently offers two github vocabularies at opposite extremes:

    github_topic  189,739 distinct topics -- free-text, whatever the owner typed
    gh_category       264 distinct        -- curated, but only where a rater looked

Neither answers "who works in AI" well. The first is too granular and noisy
(`ai`, `ai-agent`, `aiagents`, `artificial-intelligence` are four topics); the
second is precise but covers only rated repos.

`l1_route.family_tags` sits between them -- a small set of domain families
applied by the router across the whole corpus:

    sqlite> select count(*), sum(family_tags not in ('[]','')) from l1_route;
    465192|271004

    ["Backend / Web Frameworks"]|16467      ["AI / Machine Learning Core"]|10706
    ["Mobile (iOS / Android)"]|16395        ["Web Frontend"]|16302

PROVENANCE IS PRESERVED, NOT FLATTENED. `match_source` records how each routing
was decided, and the two methods are not equally trustworthy:

    topic|142718   -- matched on declared repo topics
    desc |128286   -- matched on description text
    none |194188   -- no family assigned

A description match is a weaker claim than a topic match, so it is written at a
lower weight rather than being asserted as equivalent. Consumers can filter on
weight; nothing is silently levelled up.

`bucket` (clean 158,532 / ambiguous 112,472 / dark 194,188) is the router's own
confidence in its routing. Ambiguous routings are loaded -- with a further
weight reduction -- because "we routed this three ways and could not choose" is
real information; dark rows carry no family at all and are skipped naturally.

Written under scheme='gh_family' so it never mixes with github_topic or
gh_category. A query wanting breadth asks gh_family; one wanting precision asks
gh_category. Both now exist.

This loader NEVER creates people. Unmatched owners are counted and skipped.

Usage:
  load_family_topics.py --identity identity.sqlite --graph people_v2.sqlite [--apply]
"""
import argparse
import json
import sqlite3
import sys
import time

# A topic-matched, cleanly-routed family is the strongest form of this claim.
# Everything else is a discount off that, so weight encodes trust rather than
# the loader pretending all routings are equal.
WEIGHT = {("topic", "clean"): 1.0, ("topic", "ambiguous"): 0.6,
          ("desc", "clean"): 0.7, ("desc", "ambiguous"): 0.4}


def load(identity_db, graph_db, apply_changes, include_ambiguous=True):
    src = sqlite3.connect(f"file:{identity_db}?mode=ro", uri=True)
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")

    before = {
        "gh_family_rows": g.execute(
            "SELECT COUNT(*) FROM person_topic WHERE scheme='gh_family'"
        ).fetchone()[0],
        "person_topic_total": g.execute(
            "SELECT COUNT(*) FROM person_topic"
        ).fetchone()[0],
    }

    known = {}
    for pid, value in g.execute(
        "SELECT person_id, value FROM external_ids WHERE platform='github_login'"
    ):
        known[(value or "").lower()] = pid

    rows = src.execute(
        "SELECT full_name, family_tags, match_source, bucket FROM l1_route "
        "WHERE family_tags IS NOT NULL AND family_tags NOT IN ('[]','') "
        "  AND full_name LIKE '%/%'"
    ).fetchall()

    # (person, family) -> best weight seen. A person with ten repos in one
    # family gets ONE topic row at their strongest evidence, not ten rows --
    # person_topic is about the person, not a per-repo tally.
    best = {}
    stats = {
        "source_rows": len(rows), "owner_missing": 0,
        "skipped_ambiguous": 0, "bad_json": 0,
    }
    for full_name, tags_json, match_source, bucket in rows:
        if bucket == "ambiguous" and not include_ambiguous:
            stats["skipped_ambiguous"] += 1
            continue
        login, _, _ = full_name.partition("/")
        if not login:
            continue
        pid = known.get(login.lower())
        if not pid:
            stats["owner_missing"] += 1
            continue
        try:
            families = json.loads(tags_json)
        except (ValueError, TypeError):
            stats["bad_json"] += 1
            continue
        if not isinstance(families, list):
            continue
        w = WEIGHT.get((match_source, bucket), 0.3)
        for fam in families:
            if not fam or not isinstance(fam, str):
                continue
            k = (pid, fam.strip())
            if w > best.get(k, 0.0):
                best[k] = w

    topic_rows = [
        (pid, fam, "gh_family", round(w, 3), "l1_route")
        for (pid, fam), w in best.items()
    ]

    summary = dict(stats)
    summary.update({
        "topic_rows": len(topic_rows),
        "distinct_people": len({p for p, _ in best}),
        "distinct_families": len({f for _, f in best}),
        "before": before,
        "applied": bool(apply_changes),
    })

    if apply_changes:
        g.executemany(
            "INSERT OR IGNORE INTO person_topic "
            "(person_id,topic,scheme,weight,source) VALUES (?,?,?,?,?)",
            topic_rows,
        )
        g.commit()
        summary["after"] = {
            "gh_family_rows": g.execute(
                "SELECT COUNT(*) FROM person_topic WHERE scheme='gh_family'"
            ).fetchone()[0],
            "person_topic_total": g.execute(
                "SELECT COUNT(*) FROM person_topic"
            ).fetchone()[0],
        }

    g.close()
    src.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--identity", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--no-ambiguous", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = load(a.identity, a.graph, a.apply, not a.no_ambiguous)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
