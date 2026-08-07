"""Load Wikidata human records into the people graph as external identifiers.

WHY THIS EXISTS
---------------
The graph holds PEOPLE WHO PRODUCED SOMETHING. Wikidata's P-namespace carries
the cross-platform identifiers that turn a name into a joinable entity -- ORCID,
VIAF, ISNI, X handle, Google Scholar, Goodreads -- and Wikidata itself is one of
the two authority identifiers the schema names as safe for auto-acceptance.
A person with a Wikidata QID is no longer "two humans named John Murray could
collapse" territory: that QID is unambiguous.

The schema's header names VIAF, Wikidata and ISNI as the deliberately-listed
authority identifiers -- "Plato as a string is ambiguous; VIAF 108159964 is
not. Populating these is how cross-domain stitch gets past its current count of
3." This loader populates them, plus the four most common voluntary IDs
(GitHub, ORCID, X, Google Scholar) and Goodreads, in one pass per record.

INPUT FORMAT
------------
A JSONL file: one JSON object per line. Each object must carry at least the
Wikidata QID and may carry any subset of the platform properties listed below.
Property keys are P-numbers (as strings or ints). The loader does not download
or call Wikidata -- the caller supplies the extracted records.

WHAT THIS WRITES:

  1. external_ids row, platform='wikidata', value=<QID>, for every record.
     Wikidata's own QID is the load-bearing authority id.

  2. external_ids row per P-property mapped to a known platform:
        P2037 -> 'github_login'
        P496  -> 'orcid'
        P2002 -> 'x_handle'
        P1960 -> 'google_scholar'
        P214  -> 'viaf'
        P213  -> 'isni'
        P2963 -> 'goodreads'
     Confidence is 1.0 for an authority file (VIAF/ISNI/Wikidata), 0.9 for the
     platforms a person self-asserted (GitHub/ORCID/X/Scholar/Goodreads).

  3. person.birth_year / person.death_year from P569 / P570, but ONLY where
     currently NULL. Negative years are preserved (Plato = -428). The schema
     explicitly supports BCE.

MATCHING LAW: where a Wikidata record carries a GitHub login (P2037) that
matches an existing 'gh:<login>' person, that person_id is used. Where no
GitHub match exists, the loader DOES NOT silently mint a person -- it writes
an identity_claim with method='authority_file', confidence=0.95, evidence
listing the QID and any identifiers seen, status='proposed'. A downstream
matcher or human decides whether to promote. This is the same law the schema
states for identity_claim: only shared_external_id and authority_file justify
auto-acceptance, and a single authority file without a secondary anchor is
proposed, not auto-accepted.

Usage:
  load_wikidata_identities.py --wikidata records.jsonl --graph people_v2.sqlite [--apply]
"""
import argparse
import json
import os
import sqlite3
import sys
import time

# Wikidata property id -> external_ids platform name.
# Confidence is 1.0 for authority files, 0.9 for self-asserted platforms --
# Wikidata's reference graph already separates those, and the schema's law on
# identity_claim says authority_file justifies auto-acceptance while a single
# shared handle does not.
PROPERTY_TO_PLATFORM = {
    "P2037": ("github_login", 0.9),
    "P496":  ("orcid", 0.9),
    "P2002": ("x_handle", 0.9),
    "P1960": ("google_scholar", 0.9),
    "P214":  ("viaf", 1.0),
    "P213":  ("isni", 1.0),
    "P2963": ("goodreads", 0.9),
}
PROPERTIES_BIRTH = "P569"
PROPERTIES_DEATH = "P570"


def load(wikidata_path, graph_db, apply_changes, limit=0):
    if not os.path.exists(wikidata_path):
        raise SystemExit(f"missing input file: {wikidata_path}")

    # The graph is WAL and another loader may hold a long write batch against
    # it. Waiting is correct here -- this loader is idempotent and not urgent,
    # whereas killing a running API grind throws away rate-limited work.
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")

    # --- before ------------------------------------------------------------
    # json_extract on a path is the safe way to count "has wikidata id": LIKE
    # would match VALUES too, which is the documented bug in load_repo_value.
    before = {
        "wikidata_external_ids": g.execute(
            "SELECT COUNT(*) FROM external_ids WHERE platform='wikidata'"
        ).fetchone()[0],
        "viaf_external_ids": g.execute(
            "SELECT COUNT(*) FROM external_ids WHERE platform='viaf'"
        ).fetchone()[0],
        "isni_external_ids": g.execute(
            "SELECT COUNT(*) FROM external_ids WHERE platform='isni'"
        ).fetchone()[0],
        "proposed_claims": g.execute(
            "SELECT COUNT(*) FROM identity_claim "
            "WHERE method='authority_file' AND evidence LIKE 'wikidata%'"
        ).fetchone()[0],
    }

    # Known gh_logins -> person_id. Same join key the owner and crates
    # loaders used; re-using it means a Wikidata record whose GitHub login
    # is already in the graph gets attached, not duplicated.
    known_gh = {}
    for pid, value in g.execute(
        "SELECT person_id, value FROM external_ids WHERE platform='github_login'"
    ):
        known_gh[(value or "").lower()] = pid

    # Known wikidata QIDs -> person_id, so we can detect "already attached".
    known_qid = {}
    for pid, value in g.execute(
        "SELECT person_id, value FROM external_ids WHERE platform='wikidata'"
    ):
        if value:
            known_qid[value] = pid

    # Persons missing birth or death, so we only UPDATE rows that still need
    # the field -- the schema's law is "never overwrite".
    missing_years = {"birth": [], "death": []}
    for pid, b, d in g.execute(
        "SELECT person_id, birth_year, death_year FROM person"
    ):
        if b is None:
            missing_years["birth"].append(pid)
        if d is None:
            missing_years["death"].append(pid)

    ext_id_rows = []        # (person_id, platform, value, confidence, source)
    claim_rows = []         # (person_a, person_b, method, confidence, evidence, status, created_at)
    year_updates = []       # (birth_year, death_year, person_id)
    stats = {
        "records_seen": 0,
        "matched_to_graph": 0,
        "already_attached": 0,
        "unmatched_proposed_claim": 0,
        "birth_year_writes": 0,
        "death_year_writes": 0,
    }

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    with open(wikidata_path, "r", encoding="utf-8") as f:
        for line in f:
            if limit and stats["matched_to_graph"] >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            stats["records_seen"] += 1

            qid = rec.get("qid") or rec.get("QID")
            if not qid:
                continue

            # Collect every property value the record carries. Wikidata JSON
            # can be either {"P2037": "torvalds"} or {"P2037": {"value": "..."}}
            # depending on the extractor -- normalise.
            def _prop(code):
                v = rec.get(code)
                if isinstance(v, dict):
                    v = v.get("value")
                return v

            gh_login = _prop("P2037")
            gh_login = gh_login.strip() if isinstance(gh_login, str) else None

            # Already attached to a person via a prior run? Nothing to do.
            existing_pid = known_qid.get(qid)
            if existing_pid:
                stats["already_attached"] += 1
                # Still record additional identifiers the record carries --
                # a second run may add ORCID/VIAF that was absent earlier.
                pid = existing_pid
                matched = True
            elif gh_login:
                pid = known_gh.get(gh_login.lower())
                if pid:
                    matched = True
                    stats["matched_to_graph"] += 1
                else:
                    matched = False
            else:
                matched = False
                pid = None

            if not matched:
                # Per the schema's law: a single authority-file match without
                # a secondary anchor is PROPOSED, not auto-accepted. Sentinel
                # pairing satisfies the CHECK(person_a < person_b) constraint
                # while the evidence still records the real proposed pid.
                proposed_pid = f"wd:{qid}"
                a = "unmatched:wikidata"
                b = proposed_pid
                claim_rows.append((
                    a, b, "authority_file", 0.95,
                    f"wikidata qid={qid}; github_login={gh_login or '-'}",
                    "proposed", now,
                ))
                stats["unmatched_proposed_claim"] += 1
                continue

            # Attach every property the record carries.
            ext_id_rows.append((pid, "wikidata", qid, 1.0, "wikidata_dump"))
            for prop, (platform, conf) in PROPERTY_TO_PLATFORM.items():
                v = _prop(prop)
                if not v:
                    continue
                ext_id_rows.append((pid, platform, str(v), conf, "wikidata_dump"))

            # Biography: only fill where currently NULL. Negative years
            # survive -- the schema explicitly supports BCE.
            birth = _prop(PROPERTIES_BIRTH)
            death = _prop(PROPERTIES_DEATH)
            if birth is not None and pid in missing_years["birth"]:
                try:
                    year_updates.append((int(birth), None, pid))
                    stats["birth_year_writes"] += 1
                except (TypeError, ValueError):
                    pass
            if death is not None and pid in missing_years["death"]:
                try:
                    year_updates.append((None, int(death), pid))
                    stats["death_year_writes"] += 1
                except (TypeError, ValueError):
                    pass

    # De-duplicate claim rows. Same person+evidence cannot propose twice.
    seen_claims = set()
    final_claims = []
    for a, b, method, conf, evidence, status, created in claim_rows:
        key = (a, b, evidence)
        if key in seen_claims:
            continue
        seen_claims.add(key)
        final_claims.append((a, b, method, conf, evidence, status, created))

    summary = {
        "records_seen": stats["records_seen"],
        "matched_to_graph": stats["matched_to_graph"],
        "already_attached": stats["already_attached"],
        "unmatched_proposed_claim": stats["unmatched_proposed_claim"],
        "external_ids_to_write": len(ext_id_rows),
        "identity_claims_proposed": len(final_claims),
        "birth_year_writes": stats["birth_year_writes"],
        "death_year_writes": stats["death_year_writes"],
        "before": before,
        "applied": bool(apply_changes),
    }

    if apply_changes:
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
        # Year updates: only the fields still NULL, written one column at a
        # time so a person with birth but not death gets only the death write.
        for birth, death, pid in year_updates:
            if birth is not None:
                g.execute(
                    "UPDATE person SET birth_year=? "
                    "WHERE person_id=? AND birth_year IS NULL",
                    (birth, pid),
                )
            if death is not None:
                g.execute(
                    "UPDATE person SET death_year=? "
                    "WHERE person_id=? AND death_year IS NULL",
                    (death, pid),
                )
        g.commit()
        summary["after"] = {
            "wikidata_external_ids": g.execute(
                "SELECT COUNT(*) FROM external_ids WHERE platform='wikidata'"
            ).fetchone()[0],
            "viaf_external_ids": g.execute(
                "SELECT COUNT(*) FROM external_ids WHERE platform='viaf'"
            ).fetchone()[0],
            "isni_external_ids": g.execute(
                "SELECT COUNT(*) FROM external_ids WHERE platform='isni'"
            ).fetchone()[0],
            "proposed_claims": g.execute(
                "SELECT COUNT(*) FROM identity_claim "
                "WHERE method='authority_file' AND evidence LIKE 'wikidata%'"
            ).fetchone()[0],
        }

    g.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wikidata", required=True,
                    help="path to a JSONL file of Wikidata human records")
    ap.add_argument("--graph", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = load(a.wikidata, a.graph, a.apply, a.limit)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
