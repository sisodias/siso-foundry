#!/usr/bin/env python3
"""Load awesome-list editorial signal into the people graph.

WHY THIS EXISTS
---------------
Stars are a popularity vote by anyone who clicked a button. Inclusion in a
curated "awesome" list is a different and scarcer signal: a human editor read
the thing and chose to cite it. When N independent editors cite the same repo,
that is peer validation -- the catalog calls it `list_count`.

The awesome catalog holds 1,077 lists / 204,186 entries / 135,784 repos, and a
precomputed per-owner rollup:

    sqlite> select count(*) from owner_signal;
    86475

None of it has ever reached the people graph, so "who does the community
actually cite" is not answerable today -- only "who has stars".

WHAT THIS WRITES
----------------
  1. person_topic(scheme='curated', topic='awesome-cited')
     weight = normalised citation strength. One row per owner, so it is cheap
     to filter on and does not need a schema change.

  2. person_content.meta_json.list_count / .awesome_sections
     Per-EDGE, on the repos that were actually cited. An owner with one
     heavily-cited repo is a different claim from one with fifty lightly-cited
     repos, and only per-edge data preserves that difference.

WEIGHTING. n_lists (how many DISTINCT lists cite them) is the honest signal,
not n_entries (total citations) -- a single list citing one owner forty times
is one editor's opinion, not forty. Normalised by a log so sindresorhus at 297
lists does not flatten everyone else to zero.

ORGANISATION CAVEAT. The top of this table is `google`, `microsoft`, `apache`.
Editorial citation tracks org output as much as individual craft, so this is
NOT a "great engineer" score and is not written as one. It is recorded as what
it is: cited-ness.

CASE. GitHub logins are case-insensitive but the catalog stores both `Microsoft`
and `microsoft` as separate owner_signal rows. They are folded on lower() and
their counts summed, matching how the graph's login index is keyed.

This loader NEVER creates people -- unmatched owners are counted and skipped.

Usage:
  load_awesome_signal.py --catalog catalog_full.sqlite --graph people_v2.sqlite [--apply]
"""
import argparse
import json
import math
import sqlite3
import sys
import time


def load(catalog_db, graph_db, apply_changes, min_lists=1):
    src = sqlite3.connect(f"file:{catalog_db}?mode=ro", uri=True)
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")

    before = {
        "person_topic_total": g.execute(
            "SELECT COUNT(*) FROM person_topic"
        ).fetchone()[0],
        "curated_awesome": g.execute(
            "SELECT COUNT(*) FROM person_topic "
            "WHERE scheme='curated' AND topic='awesome-cited'"
        ).fetchone()[0],
        "edges_with_list_count": g.execute(
            "SELECT COUNT(*) FROM person_content "
            "WHERE domain='github' AND meta_json LIKE '%list_count%'"
        ).fetchone()[0],
    }

    known = {}
    for pid, value in g.execute(
        "SELECT person_id, value FROM external_ids WHERE platform='github_login'"
    ):
        known[(value or "").lower()] = pid

    # --- owner-level signal, case-folded -----------------------------------
    folded = {}
    for owner, n_repos, n_lists, n_entries, max_repo_lists in src.execute(
        "SELECT owner, n_repos, n_lists, n_entries, max_repo_lists "
        "FROM owner_signal WHERE n_lists >= ?",
        (min_lists,),
    ):
        k = (owner or "").lower()
        if not k:
            continue
        f = folded.setdefault(
            k, {"n_repos": 0, "n_lists": 0, "n_entries": 0, "max_repo_lists": 0}
        )
        f["n_repos"] += n_repos or 0
        f["n_lists"] += n_lists or 0
        f["n_entries"] += n_entries or 0
        f["max_repo_lists"] = max(f["max_repo_lists"], max_repo_lists or 0)

    topic_rows = []
    matched_owners = 0
    unmatched_owners = 0
    for k, f in folded.items():
        pid = known.get(k)
        if not pid:
            unmatched_owners += 1
            continue
        matched_owners += 1
        # log1p keeps the long tail visible; /log1p(300) puts the busiest
        # curator (sindresorhus, 297 lists) at ~1.0.
        weight = min(1.0, math.log1p(f["n_lists"]) / math.log1p(300))
        topic_rows.append(
            (pid, "awesome-cited", "curated", round(weight, 4), "awesome_catalog")
        )

    # --- per-edge citation counts ------------------------------------------
    existing = {}
    for pid, ref, meta in g.execute(
        "SELECT person_id, content_ref, meta_json FROM person_content "
        "WHERE domain='github'"
    ):
        existing[(pid, ref)] = meta

    # Sections an owner's repos were filed under -- editor-chosen labels, a
    # cleaner topic vocabulary than raw github topics.
    sections = {}
    for target, section in src.execute(
        "SELECT target_repo, section FROM entry "
        "WHERE section IS NOT NULL AND section != ''"
    ):
        sections.setdefault(target, set()).add(section)

    edge_updates = []
    edges_matched = 0
    edges_owner_missing = 0
    for full_name, owner, list_count in src.execute(
        "SELECT full_name, owner, list_count FROM repo WHERE list_count > 0"
    ):
        pid = known.get((owner or "").lower())
        if not pid:
            edges_owner_missing += 1
            continue
        key = (pid, full_name)
        if key not in existing:
            edges_owner_missing += 1
            continue
        edges_matched += 1
        try:
            meta = json.loads(existing[key] or "{}")
        except (ValueError, TypeError):
            meta = {}
        meta["list_count"] = list_count
        secs = sorted(sections.get(full_name, ()))[:5]
        if secs:
            meta["awesome_sections"] = secs
        edge_updates.append((json.dumps(meta), pid, full_name))

    summary = {
        "owner_signal_rows": len(folded),
        "matched_owners": matched_owners,
        "unmatched_owners": unmatched_owners,
        "topic_rows": len(topic_rows),
        "edges_matched": edges_matched,
        "edges_owner_missing": edges_owner_missing,
        "before": before,
        "applied": bool(apply_changes),
    }

    if apply_changes:
        g.executemany(
            "INSERT OR IGNORE INTO person_topic "
            "(person_id,topic,scheme,weight,source) VALUES (?,?,?,?,?)",
            topic_rows,
        )
        g.executemany(
            "UPDATE person_content SET meta_json=? "
            "WHERE person_id=? AND domain='github' AND content_ref=?",
            edge_updates,
        )
        g.commit()
        summary["after"] = {
            "person_topic_total": g.execute(
                "SELECT COUNT(*) FROM person_topic"
            ).fetchone()[0],
            "curated_awesome": g.execute(
                "SELECT COUNT(*) FROM person_topic "
                "WHERE scheme='curated' AND topic='awesome-cited'"
            ).fetchone()[0],
            "edges_with_list_count": g.execute(
                "SELECT COUNT(*) FROM person_content "
                "WHERE domain='github' AND meta_json LIKE '%list_count%'"
            ).fetchone()[0],
        }

    g.close()
    src.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--min-lists", type=int, default=1)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = load(a.catalog, a.graph, a.apply, a.min_lists)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
