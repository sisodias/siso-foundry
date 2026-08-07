#!/usr/bin/env python3
"""
Organisations as a FIRST-CLASS entity, seeded from crates.io teams.

THE PROBLEM THIS FIXES.

person.kind already allows 'organisation', and 870 book "authors" are flagged as
institutions. But organisations live INSIDE the person table, which is why
microsoft, google and apache rank beside Jensen Huang in every rated-value
query. Those are not comparable things: "what does this person believe" and
"what does this company ship" are different questions, and answering them from
one table means every leaderboard silently mixes them.

An organisation is not a person with a different flag. It has members, it
outlives them, and it cannot author anything itself -- its people do.

WHY crates.io teams is the right seed.

teams.csv carries login in the shape 'github:ORG:team' -- the GitHub
organisation name is embedded, so org identity is resolved rather than guessed.
Measured on the 2026-08-04 dump: 1,559 teams, and 13,809 crate-ownership rows
with owner_kind=1 that load_crates_maintainers.py currently DROPS entirely
because minting a team as a human is exactly the error person.kind exists to
prevent.

WHAT IS CREATED.

  organisation        org_id (namespaced 'gh_org:<login>'), name, kind,
                      github_org_id, state, provenance columns
  person_organisation person <-> org edges with a relation and direction, the
                      same shape person_person uses, so employment from Wikidata
                      and team membership from crates can share one table
  organisation_content org -> artifact edges, so a team-owned crate attaches to
                      the ORG rather than being dropped or misattributed to
                      whichever human happened to publish it

DELIBERATE OMISSIONS. No organisation is merged with an existing
kind='organisation' person row. That merge is an identity claim and belongs in
identity_claim under human review -- the same law that keeps two different
"John Murray" rows from silently becoming one person. This loader only proposes.
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
import time

csv.field_size_limit(10 ** 9)

SCHEMA = """
CREATE TABLE IF NOT EXISTS organisation (
  org_id        TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  kind          TEXT NOT NULL DEFAULT 'unknown'
                  CHECK (kind IN ('company','project','foundation','team','unknown')),
  github_org_id TEXT,
  state         TEXT NOT NULL DEFAULT 'tracked'
                  CHECK (state IN ('tracked','linked','merged','disputed')),
  source        TEXT NOT NULL,
  observed_at   TEXT,
  meta_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS person_organisation (
  person_id   TEXT NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
  org_id      TEXT NOT NULL REFERENCES organisation(org_id) ON DELETE CASCADE,
  relation    TEXT NOT NULL,
  started_at  TEXT,
  ended_at    TEXT,
  confidence  REAL NOT NULL DEFAULT 0.9,
  source      TEXT NOT NULL,
  observed_at TEXT,
  meta_json   TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (person_id, org_id, relation)
);

CREATE TABLE IF NOT EXISTS organisation_content (
  org_id      TEXT NOT NULL REFERENCES organisation(org_id) ON DELETE CASCADE,
  domain      TEXT NOT NULL,
  content_ref TEXT NOT NULL,
  role        TEXT,
  source      TEXT NOT NULL,
  observed_at TEXT,
  meta_json   TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (org_id, domain, content_ref, role)
);

CREATE INDEX IF NOT EXISTS ix_org_github ON organisation(github_org_id);
CREATE INDEX IF NOT EXISTS ix_po_org ON person_organisation(org_id);
CREATE INDEX IF NOT EXISTS ix_oc_domain ON organisation_content(domain);
"""


def org_from_team_login(login):
    """'github:rust-osdev:x86_64' -> ('rust-osdev', 'x86_64'). None if unparsable."""
    if not login:
        return None
    parts = login.split(":")
    if len(parts) < 3 or parts[0] != "github":
        return None
    if not parts[1]:
        return None
    return parts[1], ":".join(parts[2:])


def counters(g):
    def n(t):
        try:
            return g.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.OperationalError:
            return 0
    return {
        "organisations": n("organisation"),
        "person_organisation": n("person_organisation"),
        "organisation_content": n("organisation_content"),
    }


def load(dump_dir, graph_db, apply_changes, limit=0):
    t0 = time.time()
    for f in ("teams.csv", "crate_owners.csv", "crates.csv"):
        if not os.path.exists(os.path.join(dump_dir, f)):
            print(f"missing required file: {f}", file=sys.stderr)
            return None

    g = sqlite3.connect(graph_db)
    g.execute("PRAGMA busy_timeout=600000")
    g.executescript(SCHEMA)
    before = counters(g)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # crate_id -> crate name, so org edges carry a readable content_ref.
    crate_name = {}
    with open(os.path.join(dump_dir, "crates.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("id") and row.get("name"):
                crate_name[row["id"]] = row["name"]

    # teams.csv: team id -> (org login, team name, github org id)
    team = {}
    orgs = {}
    with open(os.path.join(dump_dir, "teams.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            parsed = org_from_team_login(row.get("login"))
            if not parsed:
                continue
            org_login, team_name = parsed
            team[row["id"]] = (org_login, team_name)
            oid = f"gh_org:{org_login}"
            if oid not in orgs:
                orgs[oid] = (
                    oid, org_login, "unknown", row.get("org_id") or None,
                    "tracked", "crates_io_teams", now,
                    json.dumps({"first_seen_team": team_name}),
                )

    stats = {
        "teams_seen": len(team),
        "organisations_new": 0,
        "team_owned_crates": 0,
        "org_content_edges": 0,
        "unparsable_team_logins": 0,
    }

    # owner_kind=1 rows are team-owned crates -- the ones the person loader drops.
    org_edges = []
    with open(os.path.join(dump_dir, "crate_owners.csv"), newline="",
              encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("owner_kind") or "").strip() != "1":
                continue
            stats["team_owned_crates"] += 1
            t = team.get(row.get("owner_id") or "")
            if not t:
                stats["unparsable_team_logins"] += 1
                continue
            cname = crate_name.get(row.get("crate_id") or "")
            if not cname:
                continue
            org_edges.append((
                f"gh_org:{t[0]}", "crates", cname, "owner",
                "crates_io_teams", now,
                json.dumps({"team": t[1]}),
            ))

    stats["organisations_new"] = len(orgs)
    stats["org_content_edges"] = len(org_edges)
    stats["before"] = before

    if apply_changes:
        g.executemany(
            "INSERT OR IGNORE INTO organisation "
            "(org_id,name,kind,github_org_id,state,source,observed_at,meta_json) "
            "VALUES (?,?,?,?,?,?,?,?)", list(orgs.values()))
        g.executemany(
            "INSERT OR IGNORE INTO organisation_content "
            "(org_id,domain,content_ref,role,source,observed_at,meta_json) "
            "VALUES (?,?,?,?,?,?,?)", org_edges)
        g.commit()
        stats["after"] = counters(g)
    stats["applied"] = bool(apply_changes)
    stats["elapsed_s"] = round(time.time() - t0, 2)
    return stats


def main():
    ap = argparse.ArgumentParser(
        description="Seed the organisation entity from crates.io teams.")
    ap.add_argument("--dump", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    s = load(a.dump, a.graph, a.apply, a.limit)
    if s is None:
        return 1
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
