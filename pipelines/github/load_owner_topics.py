#!/usr/bin/env python3
"""Give GitHub people topics and value, from data already sitting in the corpus.

Two things the GitHub domain already computed and the people graph was throwing
away:

  1. TOPICS. repo_card.topics_json holds GitHub's own topic tags per repo
     ("sqlite", "python", "datasets"), plus `language`. Books people get topics
     from librarian-assigned LCSH subjects -- 167,585 edges -- so GitHub people
     having none made the two populations incomparable. A question like "who
     works on databases" could reach book authors and not a single engineer.

  2. VALUE. repo_category holds 385,964 rows of MiniMax-rated repos with
     reuse_value, info_value and overall_value. That is a judgement already paid
     for. Rolling it up per owner gives a defensible ranking of PEOPLE by the
     rated quality of what they produced, rather than by raw star count, which
     mostly measures popularity and age.

Both land in person_topic, the same table books uses, so a topic query spans
domains instead of stopping at one. scheme= records provenance: 'github_topic'
and 'github_lang' are GitHub's own tags; 'lcsh' is the library taxonomy. Never
merge the vocabularies -- "python" and "Philosophy, Ancient" are not the same
kind of fact, and flattening them would make both untrustworthy.

Usage:
  load_owner_topics.py --identity identity.sqlite --graph people_v2.sqlite --apply
"""
import argparse
import json
import sqlite3
import sys
import time
from collections import defaultdict

# Topics too generic to carry signal. Tagging someone "javascript" says little;
# tagging them "compilers" says a lot. Kept short deliberately -- over-filtering
# is worse than a few weak tags, because the weight column already ranks them.
NOISE = {
    "awesome", "list", "lists", "hacktoberfest", "github", "opensource",
    "open-source", "tutorial", "example", "examples", "demo", "test",
    "boilerplate", "starter", "template", "library", "framework", "tool",
    "tools", "app", "api", "cli", "web", "software",
}


def load(identity_db, graph_db, min_stars, apply_changes):
    src = sqlite3.connect(f"file:{identity_db}?mode=ro", uri=True)
    g = sqlite3.connect(graph_db)

    # Which logins are actually in the graph -- no point computing topics for
    # owners we never loaded.
    known = set()
    for (pid,) in g.execute("SELECT person_id FROM person WHERE person_id LIKE 'gh:%'"):
        known.add(pid[3:].lower())

    topics = defaultdict(lambda: defaultdict(int))   # login -> topic -> count
    langs = defaultdict(lambda: defaultdict(int))

    for full_name, topics_json, lang in src.execute(
        "SELECT full_name, topics_json, language FROM repo_card "
        "WHERE full_name LIKE '%/%' AND COALESCE(stars,0) >= ?",
        (min_stars,),
    ):
        login = full_name.split("/", 1)[0].lower()
        if login not in known:
            continue
        if lang:
            langs[login][lang] += 1
        if not topics_json:
            continue
        try:
            for t in json.loads(topics_json):
                t = (t or "").strip().lower()
                if t and t not in NOISE and len(t) > 2:
                    topics[login][t] += 1
        except (ValueError, TypeError):
            continue

    # Value roll-up: the mean rated value of an owner's repos, weighted by how
    # many were rated. A single 9/10 repo is weaker evidence than twenty 7s.
    value = {}
    try:
        for full_name, n, avg_overall, avg_reuse in src.execute(
            """SELECT full_name, COUNT(*), AVG(overall_value), AVG(reuse_value)
               FROM repo_category WHERE full_name LIKE '%/%'
               GROUP BY full_name"""
        ):
            login = full_name.split("/", 1)[0].lower()
            if login not in known:
                continue
            cur = value.setdefault(login, {"rated": 0, "sum": 0.0, "reuse": 0.0})
            cur["rated"] += n
            cur["sum"] += (avg_overall or 0) * n
            cur["reuse"] += (avg_reuse or 0) * n
    except sqlite3.Error:
        pass  # repo_category absent on some machines; topics still work

    rows = []
    for login, ts in topics.items():
        for t, n in sorted(ts.items(), key=lambda kv: -kv[1])[:25]:
            rows.append((f"gh:{login}", t, "github_topic", float(n), "repo_card"))
    for login, ls in langs.items():
        for l, n in sorted(ls.items(), key=lambda kv: -kv[1])[:8]:
            rows.append((f"gh:{login}", l, "github_lang", float(n), "repo_card"))

    summary = {
        "owners_in_graph": len(known),
        "owners_with_topics": len(topics),
        "owners_with_value": len(value),
        "topic_edges": len(rows),
        "applied": bool(apply_changes),
    }

    if apply_changes:
        # person_topic uses the login-cased id; graph rows may differ in case,
        # so resolve against what actually exists rather than assuming.
        real = {}
        for pid, in g.execute("SELECT person_id FROM person WHERE person_id LIKE 'gh:%'"):
            real[pid.lower()] = pid
        fixed = [(real.get(r[0].lower(), r[0]),) + r[1:] for r in rows]
        g.executemany(
            "INSERT OR IGNORE INTO person_topic "
            "(person_id,topic,scheme,weight,source) VALUES (?,?,?,?,?)",
            fixed,
        )
        for login, v in value.items():
            pid = real.get(f"gh:{login}", f"gh:{login}")
            if v["rated"]:
                g.execute(
                    "UPDATE person SET rank_score = COALESCE(rank_score,0) + ? "
                    "WHERE person_id = ?",
                    (v["sum"] / v["rated"], pid),
                )
        g.commit()
        summary["person_topic_total"] = g.execute(
            "SELECT COUNT(*) FROM person_topic"
        ).fetchone()[0]

    g.close()
    src.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--identity", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--min-stars", type=int, default=100)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = load(a.identity, a.graph, a.min_stars, a.apply)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
