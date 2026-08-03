#!/usr/bin/env python3
"""Propose identity claims — the thing that turns a wide graph into a useful one.

The problem, made concrete: the graph holds "Baruch Spinoza" (registry, S-tier,
zero works attached) and "Spinoza, Benedictus de, 1632-1677" (books, 13 works).
Same human. Two rows. Asking "who is Spinoza" returns the empty one first, and
"who were his contemporaries" returns nothing, because the record that carries
his dates is a different row from the one the registry curated.

Multiply that across 35,834 people and 3 domains and you get the current state:
exactly 3 humans stitched across domains, not because the data is missing but
because nothing has ever asserted that two records are the same person.

This proposes those assertions. It does NOT merge. Every output is a row in
identity_claim with a method, a confidence, and the literal evidence that
triggered it, so a human or a gate can accept or reject it and a wrong claim
costs one DELETE rather than a corrupted entity table.

Why proposals rather than merges: name matching is unsafe at scale. Two humans
named "John Murray" would silently become one person and the graph would assert
something false forever. The books merge earlier today matched 223 people by
normalised name and happened to produce zero collisions -- verified -- but that
is luck, not a method you can run on a million people.

METHODS, in descending trustworthiness:
  shared_external_id  same github login / channel id / VIAF. Near-certain: these
                      are platform-issued identifiers, not human-chosen strings.
  name_plus_years     surname + given name + overlapping life dates. Strong for
                      historical people, where dates are the disambiguator.
  surname_initial     surname + first initial + no conflicting dates. Weak;
                      proposed for review, never auto-accepted.
  exact_name          identical normalised names, no other signal. Weakest.
                      A hypothesis to look at, nothing more.

Usage:
  match_identities.py --graph people_v2.sqlite            # propose (dry run)
  match_identities.py --graph people_v2.sqlite --apply    # write claims
  match_identities.py --graph people_v2.sqlite --accept shared_external_id
"""
import argparse
import json
import re
import sqlite3
import sys
import time
from collections import defaultdict

# Honorifics and role suffixes that carry no identity information but block
# naive string equality: "Lytton, Edward Bulwer Lytton, Baron" vs "Bulwer-Lytton".
NOISE = re.compile(
    r"\b(sir|dame|lord|lady|baron|baroness|earl|duke|rev|dr|prof|jr|sr|"
    r"saint|st|mrs|mr|ms|of|the)\b",
    re.IGNORECASE,
)


def norm_name(s):
    """Normalise for comparison. Deliberately lossy, never used as an id."""
    s = (s or "").lower()
    s = re.sub(r"\([^)]*\)", " ", s)      # drop "(John Fitzgerald)"
    s = re.sub(r"[^a-z\s,]", " ", s)
    s = NOISE.sub(" ", s)
    return " ".join(s.split())


def name_parts(s):
    """(surname, given) from either 'Surname, Given' or 'Given Surname'."""
    n = norm_name(s)
    if "," in n:
        a, _, b = n.partition(",")
        return a.strip(), b.strip()
    toks = n.split()
    if len(toks) >= 2:
        return toks[-1], " ".join(toks[:-1])
    return n, ""


def years_compatible(a, b):
    """True when two life-date pairs could describe the same person.

    Missing dates are compatible with anything -- absence of evidence is not
    evidence of difference. Present dates must agree within a small tolerance,
    since catalogs disagree by a year or two on older figures.
    """
    (ab, ad), (bb, bd) = a, b
    if ab is not None and bb is not None and abs(ab - bb) > 2:
        return False
    if ad is not None and bd is not None and abs(ad - bd) > 2:
        return False
    return True


def propose(graph_db, apply_changes, auto_accept):
    con = sqlite3.connect(graph_db)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    people = con.execute(
        "SELECT person_id, name, birth_year, death_year, origin, state "
        "FROM person WHERE state != 'merged'"
    ).fetchall()

    by_extid = defaultdict(list)
    for pid, platform, value in con.execute(
        "SELECT person_id, platform, value FROM external_ids"
    ):
        by_extid[(platform, (value or "").lower())].append(pid)

    by_name = defaultdict(list)
    by_surname = defaultdict(list)
    meta = {}
    for pid, name, b, d, origin, state in people:
        meta[pid] = (name, b, d, origin)
        by_name[norm_name(name)].append(pid)
        sur, giv = name_parts(name)
        if sur:
            by_surname[(sur, giv[:1])].append(pid)

    claims = {}

    def add(a, b, method, conf, evidence):
        if a == b:
            return
        key = tuple(sorted((a, b)))
        # Keep the strongest claim for any pair; a weak signal must never
        # downgrade a strong one.
        if key not in claims or claims[key][1] < conf:
            claims[key] = (method, conf, evidence)

    # 1. Shared platform identifier. Strongest signal available.
    for (platform, value), pids in by_extid.items():
        if len(pids) > 1:
            for i in range(len(pids)):
                for j in range(i + 1, len(pids)):
                    add(pids[i], pids[j], "shared_external_id", 0.98,
                        f"{platform}={value}")

    # 2. Same normalised name. Split by whether life dates corroborate.
    for nkey, pids in by_name.items():
        if len(pids) < 2 or not nkey:
            continue
        for i in range(len(pids)):
            for j in range(i + 1, len(pids)):
                a, b = pids[i], pids[j]
                na, ba, da, oa = meta[a]
                nb, bb, db, ob = meta[b]
                if not years_compatible((ba, da), (bb, db)):
                    continue  # same name, different lives -> different humans
                if (ba or da) and (bb or db):
                    add(a, b, "name_plus_years", 0.90,
                        f"{na} [{ba}-{da}] == {nb} [{bb}-{db}]")
                elif oa != ob:
                    # Same name, no dates, but seen in DIFFERENT domains -- which
                    # is exactly the cross-domain case worth surfacing.
                    add(a, b, "exact_name", 0.55,
                        f"{na} ({oa}) == {nb} ({ob})")

    # 3. Surname + first initial, dates compatible. Catches inverted forms like
    #    "Baruch Spinoza" vs "Spinoza, Benedictus de" only when dates allow.
    for (sur, init), pids in by_surname.items():
        if len(pids) < 2 or len(sur) < 4:
            continue  # short surnames collide too often to be evidence
        for i in range(len(pids)):
            for j in range(i + 1, len(pids)):
                a, b = pids[i], pids[j]
                na, ba, da, oa = meta[a]
                nb, bb, db, ob = meta[b]
                if oa == ob:
                    continue  # within one domain, dedup is that loader's job
                if not years_compatible((ba, da), (bb, db)):
                    continue
                add(a, b, "surname_initial", 0.45,
                    f"{na} ({oa}) ~ {nb} ({ob}) surname={sur}")

    rows = [
        (a, b, m, c, e, "accepted" if (auto_accept and m == auto_accept)
         else "proposed", now)
        for (a, b), (m, c, e) in claims.items()
    ]

    summary = {
        "people_considered": len(people),
        "claims_proposed": len(rows),
        "by_method": {},
        "applied": bool(apply_changes),
    }
    for _, _, m, _, _, _, _ in rows:
        summary["by_method"][m] = summary["by_method"].get(m, 0) + 1

    if apply_changes:
        con.executemany(
            "INSERT OR IGNORE INTO identity_claim "
            "(person_a,person_b,method,confidence,evidence,status,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            rows,
        )
        con.commit()
        summary["claims_in_db"] = con.execute(
            "SELECT COUNT(*) FROM identity_claim"
        ).fetchone()[0]

    summary["samples"] = [
        {"method": m, "confidence": c, "evidence": e}
        for (_, _), (m, c, e) in sorted(
            claims.items(), key=lambda kv: -kv[1][1]
        )[:8]
    ]
    con.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument(
        "--accept",
        help="auto-accept this method only (shared_external_id is the safe one)",
    )
    a = ap.parse_args()
    print(json.dumps(propose(a.graph, a.apply, a.accept), indent=2,
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
