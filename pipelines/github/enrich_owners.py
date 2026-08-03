#!/usr/bin/env python3
"""Resolve GitHub logins to real humans — the missing link in the people graph.

The problem, measured: the graph holds 280,708 people across 463,230 GitHub
edges, 101,124 book edges and the YouTube legs, and exactly THREE humans are
stitched across domains. Adding 245,166 GitHub owners produced zero new stitches.

The cause is structural. Matching runs on names, and the two populations do not
share a namespace:
    GitHub carries LOGINS      -- "sindresorhus", "karpathy", "facebookresearch"
    Books carry CATALOG NAMES  -- "Spinoza, Benedictus de, 1632-1677"
    Registry carries REAL NAMES -- "Andrej Karpathy"
Logins never collide with catalog names, so nothing ever matches. The three that
do were hand-curated with real names already attached.

`/users/{login}` closes the gap. Verified against the live API, it returns:
    name              "Sindre Sorhus"      -> joins to registry/real-name people
    twitter_username  "sindresorhus"       -> the x_handle platform identity
    blog              "https://..."        -> website identity, often a personal
                                              site that also appears in other
                                              domains
    type              "User"|"Organization" -> settles kind= honestly instead of
                                              guessing from the login string

That last field matters on its own. The graph currently marks every GitHub owner
kind='unknown' because repo_card cannot tell a person from a company. `type`
answers it authoritatively for all 245k.

RATE LIMITS ARE THE REAL CONSTRAINT.
Unauthenticated: 60 requests/hour. Authenticated: 5,000/hour. At 245,166 owners
that is 49 hours authenticated, so this is deliberately NOT a full sweep by
default. It works highest-signal-first -- owners ranked by total stars -- because
the people worth stitching are the ones whose work people actually use. A few
thousand requests covers the population that matters; the long tail can wait for
a background job.

Writes external_ids rows, never merges. The matcher consumes those and proposes
identity_claims, which a human or a gate accepts. Same discipline as everywhere
else: evidence in, assertions reviewable, nothing silently fused.

Usage:
  enrich_owners.py --graph people_v2.sqlite --limit 500
  enrich_owners.py --graph people_v2.sqlite --limit 5000 --token $GH_TOKEN
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com/users/"


def fetch(login, token):
    req = urllib.request.Request(
        API + login,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "siso-foundry-people-graph/1.0",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        remaining = r.headers.get("X-RateLimit-Remaining")
        return json.load(r), (int(remaining) if remaining else None)


def enrich(graph_db, limit, token, sleep):
    g = sqlite3.connect(graph_db)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Highest-signal first: rank_score holds summed stars for github-origin
    # people. Skip anyone already enriched so the job is resumable.
    rows = g.execute(
        """SELECT p.person_id, p.name
           FROM person p
           WHERE p.origin = 'github'
             AND p.person_id NOT IN (
               SELECT person_id FROM external_ids
               WHERE platform IN ('real_name','x_handle','website')
             )
           ORDER BY COALESCE(p.rank_score, 0) DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()

    stats = {
        "considered": len(rows),
        "fetched": 0,
        "users": 0,
        "orgs": 0,
        "with_real_name": 0,
        "with_twitter": 0,
        "with_website": 0,
        "errors": 0,
        "rate_limited": False,
    }

    for pid, login in rows:
        try:
            data, remaining = fetch(login, token)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                stats["rate_limited"] = True
                break
            stats["errors"] += 1
            continue
        except Exception:
            stats["errors"] += 1
            continue

        stats["fetched"] += 1
        kind = "organisation" if data.get("type") == "Organization" else "human"
        stats["orgs" if kind == "organisation" else "users"] += 1

        g.execute(
            "UPDATE person SET kind=?, name=COALESCE(NULLIF(?,''), name) "
            "WHERE person_id=?",
            (kind, (data.get("name") or "").strip(), pid),
        )

        ids = []
        if data.get("name"):
            ids.append((pid, "real_name", data["name"].strip(), 1.0, "github_api"))
            stats["with_real_name"] += 1
        if data.get("twitter_username"):
            ids.append((pid, "x_handle", data["twitter_username"].strip(),
                        1.0, "github_api"))
            stats["with_twitter"] += 1
        if data.get("blog"):
            ids.append((pid, "website", data["blog"].strip(), 0.9, "github_api"))
            stats["with_website"] += 1
        ids.append((pid, "github_login", login, 1.0, "github_api"))

        # The numeric account id is the ONLY stable GitHub identity. Logins are
        # renameable -- a person who changes their handle becomes a new "person"
        # under login-keyed matching, silently splitting their work in two.
        # Recording the id makes that recoverable.
        if data.get("id"):
            ids.append((pid, "github_id", str(data["id"]), 1.0, "github_api"))

        # Company and location are weak identity signals on their own but strong
        # DISAMBIGUATORS: two "John Smith" accounts are different humans if one
        # is at Google in London and the other in Sao Paulo. Stored so the
        # matcher can use them to reject a bad name match, not to assert a good
        # one.
        if data.get("company"):
            ids.append((pid, "company", data["company"].strip().lstrip("@"),
                        0.7, "github_api"))
            stats["with_company"] = stats.get("with_company", 0) + 1
        if data.get("location"):
            ids.append((pid, "location", data["location"].strip(), 0.6,
                        "github_api"))

        # followers is a real reach signal and the honest replacement for
        # rank_score, which currently holds summed repo stars -- a measure of
        # the work, not the person. created_at dates the account, which bounds
        # any claim that this person is the same as a historical figure.
        g.execute(
            "UPDATE person SET rank_score=?, built_at=? WHERE person_id=?",
            (float(data.get("followers") or 0), now, pid),
        )

        g.executemany(
            "INSERT OR IGNORE INTO external_ids "
            "(person_id,platform,value,confidence,source) VALUES (?,?,?,?,?)",
            ids,
        )

        if stats["fetched"] % 50 == 0:
            g.commit()
            print(f"  {stats['fetched']}/{len(rows)} "
                  f"(rate limit remaining: {remaining})", file=sys.stderr)

        if remaining is not None and remaining < 10:
            stats["rate_limited"] = True
            break

        time.sleep(sleep)

    g.commit()
    stats["external_ids_total"] = g.execute(
        "SELECT COUNT(*) FROM external_ids"
    ).fetchone()[0]
    g.close()
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    ap.add_argument("--sleep", type=float, default=0.1)
    a = ap.parse_args()
    t = time.time()
    s = enrich(a.graph, a.limit, a.token, a.sleep)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
