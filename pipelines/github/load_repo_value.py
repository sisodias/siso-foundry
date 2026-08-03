#!/usr/bin/env python3
"""Load rated repo value and curated categories into the people graph.

WHY THIS EXISTS
---------------
Every github edge in the graph scores a person by STARS:

    sqlite> select count(*), sum(score is not null) from person_content
            where domain='github';
    463230|463230

Stars measure fame. The identity DB has held a *rated judgement* of the same
repos all along -- 385,959 rows carrying overall_value / reuse_value /
info_value, covering 303,116 distinct repos and 170,237 distinct owners -- and
none of it ever reached the graph. So "who does the most valuable work" was
not answerable; only "who is most famous" was.

This loader closes that. Two things move in one pass over repo_category,
because they share a source row and re-reading 386k rows twice is waste:

  1. VALUE -> person_content.meta_json.value
     Written into meta_json rather than overwriting `score`. Overwriting score
     would destroy the star signal, and fame-vs-value is exactly the comparison
     that makes the data interesting (see bank_adoption_v2.fame_gap). Both
     survive; the caller picks.

  2. CATEGORY -> person_topic (scheme='gh_category')
     The 264-row `category` table is a curated taxonomy. That is a different
     kind of claim from `github_topic`, which is whatever the repo owner typed,
     so it gets its own scheme rather than being blended in.

A REPO HAS MANY CATEGORY ROWS. repo_category is UNIQUE(full_name, category_id,
role), so a repo appears once per category with role primary|secondary. Value
columns repeat across those rows. Taking MAX(overall_value) per repo is
deliberate: the ratings are per-assignment, and a repo's worth is its best
justified rating, not an average diluted by secondary tags.

PERSON RESOLUTION follows load_owners_into_people_graph.py exactly: the owner
prefix of full_name, looked up against external_ids(platform='github_login'),
falling back to 'gh:<login>'. This loader NEVER creates people -- if an owner
is not already in the graph it is skipped and counted. Creating people is the
owner loader's job, and doing it in two places is how twins appear.

Usage:
  load_repo_value.py --identity identity.sqlite --graph people_v2.sqlite [--apply]
"""
import argparse
import json
import sqlite3
import sys
import time


def load(identity_db, graph_db, apply_changes, limit=0):
    src = sqlite3.connect(f"file:{identity_db}?mode=ro", uri=True)
    # The graph is WAL and enrich_owners.py may hold a long write batch against
    # it. Waiting is correct here -- this loader is idempotent and not urgent,
    # whereas killing a running API grind throws away rate-limited work.
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")

    # --- before ------------------------------------------------------------
    before = {
        "github_edges_with_value": g.execute(
            "SELECT COUNT(*) FROM person_content "
            "WHERE domain='github' AND meta_json LIKE '%\"value\"%'"
        ).fetchone()[0],
        "person_topic_total": g.execute(
            "SELECT COUNT(*) FROM person_topic"
        ).fetchone()[0],
        "gh_category_topics": g.execute(
            "SELECT COUNT(*) FROM person_topic WHERE scheme='gh_category'"
        ).fetchone()[0],
    }

    # Known logins -> person_id. Same join key the owner loader used.
    known = {}
    for pid, value in g.execute(
        "SELECT person_id, value FROM external_ids WHERE platform='github_login'"
    ):
        known[(value or "").lower()] = pid

    # --- source: best rating per repo, plus its categories -----------------
    # MAX() over the per-assignment rows; see module docstring.
    q = """
        SELECT rc.full_name,
               MAX(rc.overall_value), MAX(rc.reuse_value), MAX(rc.info_value),
               MAX(rc.saucy), MAX(rc.liftability),
               GROUP_CONCAT(DISTINCT c.slug)
        FROM repo_category rc
        LEFT JOIN category c ON c.id = rc.category_id
        WHERE rc.full_name LIKE '%/%'
        GROUP BY rc.full_name
    """
    if limit:
        q += f" LIMIT {int(limit)}"

    value_updates = []   # (meta_patch_json, person_id, content_ref)
    topic_rows = []      # (person_id, topic, scheme, weight, source)
    seen_topic = set()
    stats = {
        "repos_rated": 0,
        "owner_not_in_graph": 0,
        "edges_matched": 0,
        "distinct_owners": set(),
    }

    # Existing github edges, so we only patch rows that exist. Pulling the
    # whole set once beats 300k point lookups.
    existing = {}
    for pid, ref, meta in g.execute(
        "SELECT person_id, content_ref, meta_json FROM person_content "
        "WHERE domain='github'"
    ):
        existing[(pid, ref)] = meta

    for full_name, overall, reuse, info, saucy, lift, slugs in src.execute(q):
        stats["repos_rated"] += 1
        login, _, _ = full_name.partition("/")
        if not login:
            continue
        pid = known.get(login.lower(), f"gh:{login}")

        key = (pid, full_name)
        if key not in existing:
            stats["owner_not_in_graph"] += 1
            continue
        stats["edges_matched"] += 1
        stats["distinct_owners"].add(pid)

        # Merge into the existing meta rather than replacing it -- language and
        # url are already in there and are still true.
        try:
            meta = json.loads(existing[key] or "{}")
        except (ValueError, TypeError):
            meta = {}
        meta["value"] = overall
        if reuse is not None:
            meta["reuse_value"] = reuse
        if info is not None:
            meta["info_value"] = info
        if saucy:
            meta["saucy"] = 1
        if lift is not None:
            meta["liftability"] = lift
        value_updates.append((json.dumps(meta), pid, full_name))

        for slug in (slugs or "").split(","):
            slug = slug.strip()
            if not slug:
                continue
            t = (pid, slug)
            if t in seen_topic:
                continue
            seen_topic.add(t)
            # Weight by the repo's own rating: a category claim backed by a
            # 90-value repo is stronger evidence than one backed by a 10.
            topic_rows.append(
                (pid, slug, "gh_category", float(overall or 0) / 100.0,
                 "repo_category")
            )

    summary = {
        "repos_rated": stats["repos_rated"],
        "edges_matched": stats["edges_matched"],
        "owner_not_in_graph": stats["owner_not_in_graph"],
        "distinct_owners_enriched": len(stats["distinct_owners"]),
        "value_updates": len(value_updates),
        "topic_rows": len(topic_rows),
        "before": before,
        "applied": bool(apply_changes),
    }

    if apply_changes:
        g.executemany(
            "UPDATE person_content SET meta_json=? "
            "WHERE person_id=? AND domain='github' AND content_ref=?",
            value_updates,
        )
        g.executemany(
            "INSERT OR IGNORE INTO person_topic "
            "(person_id,topic,scheme,weight,source) VALUES (?,?,?,?,?)",
            topic_rows,
        )
        g.commit()
        summary["after"] = {
            "github_edges_with_value": g.execute(
                "SELECT COUNT(*) FROM person_content "
                "WHERE domain='github' AND meta_json LIKE '%\"value\"%'"
            ).fetchone()[0],
            "person_topic_total": g.execute(
                "SELECT COUNT(*) FROM person_topic"
            ).fetchone()[0],
            "gh_category_topics": g.execute(
                "SELECT COUNT(*) FROM person_topic WHERE scheme='gh_category'"
            ).fetchone()[0],
        }

    g.close()
    src.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--identity", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = load(a.identity, a.graph, a.apply, a.limit)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
