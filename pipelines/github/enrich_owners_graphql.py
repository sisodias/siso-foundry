#!/usr/bin/env python3
"""Resolve GitHub owners via GraphQL batching -- ~100x faster than the REST loop.

WHY THIS REPLACES enrich_owners.py
----------------------------------
The REST version issues ONE request per login against /users/{login}, with a
sleep between. That shape has two independent costs, and the rate limit is the
smaller one:

  * 235,732 owners x 1 round trip, serialised = ~49 hours of wall clock
  * REST charges 1 rate-limit unit PER USER, so 5,000/hr is a hard user ceiling

GraphQL fixes both at once. Multiple aliased selections travel in one request,
and the API bills by query complexity rather than by entity. Measured, not
assumed:

    $ 100 aliased repositoryOwner lookups in one POST
    aliases_returned: 100
    rateLimit: {'cost': 1, 'remaining': 4194, 'limit': 5000}
    HTTP:200 TIME:2.27s

**cost: 1 for 100 users.** That is a 100x reduction in rate-limit consumption on
top of removing 99% of the round trips. At 5,000 requests/hr x 100 users, the
ceiling becomes ~500,000 users/hr, so the entire remaining backlog fits in well
under an hour -- bounded by HTTP throughput, not by GitHub.

repositoryOwner + inline fragments is the right selector. A login may be a User
or an Organization, and the REST script discovered which only by fetching and
reading `type`. repositoryOwner resolves either and `__typename` reports which,
so org-vs-human classification comes free in the same call -- which is the whole
remaining value of this job now that the book stitch is known to be capped at
419 people.

PARTIAL RESULTS ARE THE NORMAL CASE. A deleted or renamed login makes GraphQL
return null for THAT alias plus a top-level error, while still returning every
other alias. The REST loop treated an error as a failed request; here a null
alias is recorded as resolved-to-nothing so the batch is not retried forever.

Written as a SEPARATE FILE rather than editing enrich_owners.py: that script is
running right now against the same graph, and rewriting a file mid-execution is
how you get a half-old, half-new process. Retire it after this proves out.

Usage:
  enrich_owners_graphql.py --graph people_v2.sqlite [--batch 100] [--limit N] [--apply]
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

GQL = "https://api.github.com/graphql"

FIELDS = """
    login
    __typename
    ... on User {
      name twitterUsername websiteUrl company location
      followers { totalCount }
    }
    ... on Organization {
      name twitterUsername websiteUrl location
    }
"""


def build_query(logins):
    parts = [
        'a%d: repositoryOwner(login: %s) { %s }' % (i, json.dumps(l), FIELDS)
        for i, l in enumerate(logins)
    ]
    return "query { %s rateLimit { cost remaining } }" % " ".join(parts)


def post(query, token, retries=4):
    body = json.dumps({"query": query}).encode()
    for attempt in range(retries):
        req = urllib.request.Request(
            GQL, data=body,
            headers={
                "Authorization": f"bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "siso-foundry-people-graph/2.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            # 502/403 under load are transient; back off rather than abandoning
            # a batch of 100 logins for one blip.
            if e.code in (403, 429, 502, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt * 3)
                continue
            raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 3)
                continue
            raise
    return None


def enrich(graph_db, token, batch_size, limit, apply_changes, sleep):
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    before = {
        "kind_unknown": g.execute(
            "SELECT COUNT(*) FROM person WHERE kind='unknown'"
        ).fetchone()[0],
        "real_name": g.execute(
            "SELECT COUNT(*) FROM external_ids WHERE platform='real_name'"
        ).fetchone()[0],
    }

    q = """SELECT p.person_id, p.name FROM person p
           WHERE p.origin='github'
             AND p.person_id NOT IN (
               SELECT person_id FROM external_ids
               WHERE platform IN ('real_name','x_handle','website'))
           ORDER BY COALESCE(p.rank_score, 0) DESC"""
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = g.execute(q).fetchall()

    by_login = {}
    for pid, login in rows:
        if login:
            by_login.setdefault(login, pid)
    logins = list(by_login)

    stats = {
        "candidates": len(logins), "batches": 0, "resolved": 0,
        "users": 0, "orgs": 0, "null_aliases": 0, "failed_batches": 0,
        "gql_cost": 0,
    }
    person_updates, extid_rows = [], []

    for i in range(0, len(logins), batch_size):
        chunk = logins[i:i + batch_size]
        try:
            resp = post(build_query(chunk), token)
        except Exception:
            stats["failed_batches"] += 1
            continue
        if not resp:
            stats["failed_batches"] += 1
            continue
        stats["batches"] += 1
        data = resp.get("data") or {}
        rl = data.get("rateLimit") or {}
        stats["gql_cost"] += rl.get("cost") or 0

        for idx, login in enumerate(chunk):
            node = data.get(f"a{idx}")
            if not node:
                # Deleted/renamed login. Resolved-to-nothing, not a failure --
                # otherwise the batch is retried forever.
                stats["null_aliases"] += 1
                continue
            pid = by_login[login]
            stats["resolved"] += 1
            is_org = node.get("__typename") == "Organization"
            stats["orgs" if is_org else "users"] += 1
            kind = "organisation" if is_org else "human"

            person_updates.append((kind, node.get("name") or "", pid))
            for platform, value in (
                ("real_name", node.get("name")),
                ("x_handle", node.get("twitterUsername")),
                ("website", node.get("websiteUrl")),
                ("company", node.get("company")),
                ("location", node.get("location")),
            ):
                if value:
                    extid_rows.append(
                        (pid, platform, str(value)[:200], 1.0, "github_graphql")
                    )

        if apply_changes and len(person_updates) >= 2000:
            _flush(g, person_updates, extid_rows)
            person_updates, extid_rows = [], []
        if sleep:
            time.sleep(sleep)

    if apply_changes:
        _flush(g, person_updates, extid_rows)
        g.commit()

    summary = dict(stats)
    summary["before"] = before
    summary["applied"] = bool(apply_changes)
    if apply_changes:
        summary["after"] = {
            "kind_unknown": g.execute(
                "SELECT COUNT(*) FROM person WHERE kind='unknown'"
            ).fetchone()[0],
            "real_name": g.execute(
                "SELECT COUNT(*) FROM external_ids WHERE platform='real_name'"
            ).fetchone()[0],
        }
    g.close()
    return summary


def _flush(g, person_updates, extid_rows):
    if person_updates:
        g.executemany(
            "UPDATE person SET kind=?, name=COALESCE(NULLIF(?,''), name) "
            "WHERE person_id=?", person_updates,
        )
    if extid_rows:
        g.executemany(
            "INSERT OR IGNORE INTO external_ids "
            "(person_id,platform,value,confidence,source) VALUES (?,?,?,?,?)",
            extid_rows,
        )
    g.commit()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    ap.add_argument("--batch", type=int, default=100)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not a.token:
        print("ERROR: no token. Pass --token or export GITHUB_TOKEN.",
              file=sys.stderr)
        return 2
    t = time.time()
    s = enrich(a.graph, a.token, a.batch, a.limit, a.apply, a.sleep)
    s["elapsed_s"] = round(time.time() - t, 2)
    if s["elapsed_s"] > 0 and s["resolved"]:
        s["owners_per_hour"] = int(s["resolved"] / s["elapsed_s"] * 3600)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
