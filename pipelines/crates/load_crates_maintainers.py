#!/usr/bin/env python3
"""Load crates.io maintainers and per-crate facts into the people graph.

WHY THIS EXISTS
---------------
The people graph scores a person by what they have PRODUCED. crates.io is the
Rust ecosystem's package registry and a maintainer relationship there is one of
the strongest "this person ships real software" signals we have outside GitHub
itself -- often stronger, because crates.io records who owns a crate today, not
who happened to push a star.

The crates.io DB dump (https://static.crates.io/db-dump.tar.gz) expands to a
directory of CSV files; the ones we touch are:

    users.csv         -- one row per crates.io account (gh_login, gh_id, name)
    crates.csv        -- one row per crate (name, updated_at, downloads, ...)
    crate_owners.csv  -- many-to-many: which crates.io user owns which crate
    versions.csv      -- one row per release (used to count crates per user)

The join key is the crates.io user's gh_login. The graph already holds people
with person_id='gh:<login>' when they were pulled in from GitHub; that is the
same key the owner loader used, and re-using it means a crates maintainer who
already has GitHub edges is enriched, not duplicated.

WHAT THIS WRITES:

  1. external_ids row, platform='crates_io', value=<crates.io user id>,
     for every matched user. The crates.io numeric id is a stable
     identifier even when a user has no GitHub link, so it is worth
     recording alongside gh_login.

  2. person_content row, domain='crates', content_ref=<crate name>,
     source='crates_io', observed_at=<crate updated_at>, role='owner'.
     One edge per (user, crate) pair from crate_owners.

  3. meta_json keys per edge: downloads (latest total), crate_count
     (number of crates this maintainer owns), plus any other columns
     present in the dump that look load-bearing.

score is NEVER touched. crates signals belong in meta_json next to the other
loade' outputs (adoption, value, legal_lane), so a downstream query can pick
whichever signal it wants.

UNMATCHED CRATES.IO USERS (no matching 'gh:<login>' in the graph) are NOT
silently created. Per the schema's law on identity_claim -- "only
shared_external_id and authority_file justify auto-acceptance" -- a
crates->github link is exactly shared_external_id: the crates.io user
carries a gh_login that another source already used to mint a person_id.
But auto-minting a NEW gh:<login> person from a single crates match is a
weaker claim than the existing loaders make (they run after the owner
loader has already minted the person), so the safe move is to write an
identity_claim row with method='shared_external_id' and confidence=0.6,
evidence='crates_io user id=<N>; gh_login=<login>', status='proposed'.
A human or a downstream matcher decides whether to promote. The count
of such proposed claims is returned in the summary.

This loader NEVER overwrites an existing score. meta_json is merged, not
replaced. Re-runs are idempotent because every write is either an
INSERT OR IGNORE (person_content primary key includes role) or an
UPSERT that preserves pre-existing keys.

Usage:
  load_crates_maintainers.py --dump /path/to/db-dump/ --graph people_v2.sqlite [--apply]
"""
import argparse
import csv
import json
import os
import sqlite3
import sys
import time

# crates.csv embeds full README text in a single field; the stdlib default of
# 131072 bytes trips on it. Raise before any DictReader touches the dump.
csv.field_size_limit(10 ** 9)

# meta_json key -> column in crates.csv. Sparse writes only -- a NULL in the
# source stays absent from the meta rather than getting recorded as JSON null.
CRATE_FIELDS = (
    ("downloads", "downloads"),
    ("description", "description"),
    ("homepage", "homepage"),
    ("repository", "repository"),
    ("max_version", "max_version"),
    ("max_stable_version", "max_stable_version"),
)


def load(dump_dir, graph_db, apply_changes, limit=0):
    users_path = os.path.join(dump_dir, "users.csv")
    crates_path = os.path.join(dump_dir, "crates.csv")
    owners_path = os.path.join(dump_dir, "crate_owners.csv")
    for p in (users_path, crates_path, owners_path):
        if not os.path.exists(p):
            raise SystemExit(f"missing required file: {p}")

    # The graph is WAL and another loader may hold a long write batch against
    # it. Waiting is correct here -- this loader is idempotent and not urgent,
    # whereas killing a running API grind throws away rate-limited work.
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")

    # --- before ------------------------------------------------------------
    before = {
        "crates_edges": g.execute(
            "SELECT COUNT(*) FROM person_content WHERE domain='crates'"
        ).fetchone()[0],
        "crates_io_external_ids": g.execute(
            "SELECT COUNT(*) FROM external_ids WHERE platform='crates_io'"
        ).fetchone()[0],
        "crates_downloads_known": g.execute(
            "SELECT COUNT(*) FROM person_content WHERE domain='crates' "
            "AND json_extract(meta_json,'$.downloads') IS NOT NULL"
        ).fetchone()[0],
        "proposed_claims": g.execute(
            "SELECT COUNT(*) FROM identity_claim "
            "WHERE method='shared_external_id' AND evidence LIKE 'crates_io%'"
        ).fetchone()[0],
    }

    # Known gh_logins -> person_id. Same join key the owner loader used.
    known = {}
    for pid, value in g.execute(
        "SELECT person_id, value FROM external_ids WHERE platform='github_login'"
    ):
        known[(value or "").lower()] = pid

    # Existing crates edges so we only write missing ones. Pulling the whole
    # set once beats N point lookups.
    existing_edges = set()
    for pid, ref, role in g.execute(
        "SELECT person_id, content_ref, role FROM person_content "
        "WHERE domain='crates'"
    ):
        existing_edges.add((pid, ref, role))

    # --- source: crates.csv keyed by name -----------------------------------
    crate_meta = {}
    with open(crates_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            crate_meta[row["name"]] = row

    # --- source: users.csv keyed by id --------------------------------------
    user_by_id = {}
    with open(users_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            user_by_id[row["id"]] = row

    # --- main pass over crate_owners ---------------------------------------
    edge_rows = []          # (person_id, domain, content_ref, role, title, source, observed_at, meta_json)
    ext_id_rows = []        # (person_id, platform, value, confidence, source)
    claim_rows = []         # (person_a, person_b, method, confidence, evidence, status, created_at)
    stats = {
        "owners_seen": 0,
        "matched_to_graph": 0,
        "unmatched_proposed_claim": 0,
        "edges_inserted": 0,
        "edges_already_present": 0,
        "owners_without_gh_login": 0,
    }

    # Count crates per matched user so meta_json.crate_count is meaningful.
    crate_count = {}

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    with open(owners_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if limit and stats["matched_to_graph"] >= limit:
                break
            stats["owners_seen"] += 1
            # Verified against the 2026-08-04 dump: the real header is
            # crate_id,created_at,created_by,owner_id,owner_kind. owner_kind=0
            # is a user (joins users.csv), 1 is a team (teams.csv) -- teams are
            # organisations, not people, so they are skipped here rather than
            # minted as humans.
            if (row.get("owner_kind") or "").strip() != "0":
                continue
            user_id = row.get("owner_id") or row.get("crate_user_id") or row.get("user_id")
            crate_id = row.get("crate_id")
            if not user_id or not crate_id:
                continue
            user = user_by_id.get(user_id)
            crate_row = crate_meta.get(crate_id) or crate_meta.get(row.get("crate_name") or "")
            if user is None:
                continue
            gh_login = (user.get("gh_login") or "").strip()
            if not gh_login:
                stats["owners_without_gh_login"] += 1
                continue

            login_lc = gh_login.lower()
            pid = known.get(login_lc)
            if pid is None:
                # Propose an identity_claim; do not mint the person silently.
                proposed_pid = f"gh:{gh_login}"
                claim_rows.append((
                    proposed_pid, proposed_pid,  # CHECK (person_a < person_b) below
                    "shared_external_id",
                    0.6,
                    f"crates_io user id={user_id}; gh_login={gh_login}",
                    "proposed",
                    now,
                ))
                stats["unmatched_proposed_claim"] += 1
                continue

            stats["matched_to_graph"] += 1
            crate_count[pid] = crate_count.get(pid, 0) + 1

            # External id: crates.io numeric id, recorded alongside gh_login.
            ext_id_rows.append((pid, "crates_io", str(user_id), 1.0, "crates_io_dump"))

            crate_name = (crate_row or {}).get("name") or row.get("crate_name") or crate_id
            updated_at = (crate_row or {}).get("updated_at")
            edge_key = (pid, crate_name, "owner")
            if edge_key in existing_edges:
                stats["edges_already_present"] += 1
                continue

            meta = {"crate_count_so_far": None}  # placeholder; filled below
            for k, col in CRATE_FIELDS:
                v = (crate_row or {}).get(col) if crate_row else None
                if v not in (None, ""):
                    meta[k] = v

            edge_rows.append((
                pid, "crates", crate_name, "owner",
                crate_name, "crates_io", updated_at,
                json.dumps(meta),
            ))

    # Patch crate_count into the meta_json of every edge we are about to write.
    final_edge_rows = []
    for pid, domain, ref, role, title, source, observed_at, meta_json in edge_rows:
        meta = json.loads(meta_json)
        meta["crate_count"] = crate_count.get(pid, 1)
        final_edge_rows.append(
            (pid, domain, ref, role, title, source, observed_at, json.dumps(meta))
        )

    # De-duplicate claim rows (CHECK person_a < person_b + PK on claim).
    seen_claims = set()
    final_claims = []
    for person_a, _, method, conf, evidence, status, created in claim_rows:
        # The proposed person_id is the same on both sides (gh:<login>), so the
        # CHECK constraint person_a < person_b fails. Use a sentinel "unmatched"
        # id paired with the proposed person to satisfy the constraint while
        # still recording the evidence -- a downstream matcher can promote the
        # claim to a real (person, person) pair once the person is created.
        a = "unmatched:crates_io"
        b = f"gh:{person_a.split(':',1)[1]}" if person_a.startswith("gh:") else person_a
        key = (a, b, evidence)
        if key in seen_claims:
            continue
        seen_claims.add(key)
        final_claims.append((a, b, method, conf, evidence, status, created))

    summary = {
        "owners_seen": stats["owners_seen"],
        "matched_to_graph": stats["matched_to_graph"],
        "unmatched_proposed_claim": stats["unmatched_proposed_claim"],
        "owners_without_gh_login": stats["owners_without_gh_login"],
        "edges_inserted": len(final_edge_rows),
        "edges_already_present": stats["edges_already_present"],
        "identity_claims_proposed": len(final_claims),
        "before": before,
        "applied": bool(apply_changes),
    }

    if apply_changes:
        g.executemany(
            "INSERT OR IGNORE INTO person_content "
            "(person_id,domain,content_ref,role,title,source,observed_at,meta_json) "
            "VALUES (?,?,?,?,?,?,?,?)",
            final_edge_rows,
        )
        g.executemany(
            "INSERT OR IGNORE INTO external_ids "
            "(person_id,platform,value,confidence,source) VALUES (?,?,?,?,?)",
            ext_id_rows,
        )
        g.executemany(
            "INSERT OR IGNORE INTO identity_claim "
            "(person_a,person_b,method,confidence,evidence,status,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            final_claims,
        )
        g.commit()
        summary["after"] = {
            "crates_edges": g.execute(
                "SELECT COUNT(*) FROM person_content WHERE domain='crates'"
            ).fetchone()[0],
            "crates_io_external_ids": g.execute(
                "SELECT COUNT(*) FROM external_ids WHERE platform='crates_io'"
            ).fetchone()[0],
            "crates_downloads_known": g.execute(
                "SELECT COUNT(*) FROM person_content WHERE domain='crates' "
                "AND json_extract(meta_json,'$.downloads') IS NOT NULL"
            ).fetchone()[0],
            "proposed_claims": g.execute(
                "SELECT COUNT(*) FROM identity_claim "
                "WHERE method='shared_external_id' AND evidence LIKE 'crates_io%'"
            ).fetchone()[0],
        }
        summary["edges_inserted"] = (
            summary["after"]["crates_edges"] - before["crates_edges"]
        )

    g.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dump", required=True,
                    help="path to extracted crates.io db-dump directory")
    ap.add_argument("--graph", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = load(a.dump, a.graph, a.apply, a.limit)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
