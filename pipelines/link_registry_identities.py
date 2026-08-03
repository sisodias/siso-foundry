#!/usr/bin/env python3
"""Link hand-curated registry people to their GitHub accounts.

WHY THIS EXISTS
---------------
`ask.py --who Spinoza` returns TWO people: `baruch-spinoza` (registry, 0 edges)
and `bk:spinoza, benedictus de|1632-1677` (books, 13 edges). Same human, two
person_ids, nothing connecting them. The registry layer is hand-curated and
mostly unlinked:

    sqlite> select count(*) total,
            sum(person_id in (select person_id from person_content)) with_edges
            from person where origin='registry';
    140|27

113 curated people we explicitly said we care about have no output attached.

WHY THIS IS TRACTABLE WHERE THE BOOK STITCH WAS NOT. The github<->books stitch is
measured dead (zero multi-word matches at three sample sizes; Gutenberg is a
public-domain corpus of dead people). The registry is the opposite population:
living technologists, exactly the people who have GitHub accounts. And it is
140 rows, so precision beats recall and every match can be justified.

Measured routes:
    match via github real_name : 6
    match via book name        : 0

WHAT THIS WRITES -- identity_claim rows, NOT merges.
The schema provides `person.merged_into` for merging and an `identity_claim`
table for asserting a link before acting on it. Every row is written
status='proposed'; confidence carries how sure the match is:

  * UNAMBIGUOUS (exactly one github login for the name) -> confidence 0.9
  * AMBIGUOUS  (several logins share the name)          -> confidence 0.4,
    with every candidate listed in `evidence` so a human can adjudicate

**Confidence and status are deliberately separate.** Confidence is what the
matcher believes; status is whether anyone has agreed. Collapsing them is how a
0.9 guess silently becomes a merge. Nothing here is 'accepted' -- that transition
belongs to a human, and `merged_into` being non-destructive only helps if a bad
merge was a decision someone made rather than one a loader made for them.

The table enforces `CHECK (person_a < person_b)`, so pairs are stored in
canonical order rather than registry-then-github order -- one claim per pair
regardless of which side proposed it.

WHY AMBIGUITY IS THE NORMAL CASE, NOT AN EDGE CASE:

    Andrew Ng       -> gh:andrewyng            (1 candidate, confident)
    Theo Browne     -> gh:t3dotgg              (1)
    Guillermo Rauch -> gh:rauchg               (1)
    Adam Smith      -> gh:adchsm, gh:ScriptSmith, gh:adamsmith   (3!)

"Adam Smith" is also plausibly the 18th-century economist rather than any GitHub
user at all. A loader that took the first candidate would have silently asserted
that the author of The Wealth of Nations maintains a JavaScript library. Exactly
the class of error the mononym collisions demonstrated on the books side.

Usage:
  link_registry_identities.py --graph people_v2.sqlite [--apply]
"""
import argparse
import json
import os
import sqlite3
import sys
import time


def link(graph_db, apply_changes):
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")

    before = {
        "identity_claims": g.execute(
            "SELECT COUNT(*) FROM identity_claim"
        ).fetchone()[0],
        "registry_unlinked": g.execute(
            "SELECT COUNT(*) FROM person WHERE origin='registry' "
            "AND person_id NOT IN (SELECT person_id FROM person_content)"
        ).fetchone()[0],
    }

    registry = g.execute(
        "SELECT person_id, name FROM person WHERE origin='registry' "
        "AND person_id NOT IN (SELECT person_id FROM person_content)"
    ).fetchall()

    by_name = {}
    for pid, value in g.execute(
        "SELECT person_id, value FROM external_ids WHERE platform='real_name'"
    ):
        if value:
            by_name.setdefault(value.strip().lower(), []).append(pid)

    claims, stats = [], {"confident": 0, "ambiguous": 0, "no_match": 0}
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    for pid, name in registry:
        cands = by_name.get((name or "").strip().lower())
        if not cands:
            stats["no_match"] += 1
            continue
        # De-dupe: the same login can hold several real_name rows.
        cands = sorted(set(cands))
        other = cands[0]
        if len(cands) == 1:
            stats["confident"] += 1
            conf, evidence = 0.9, (
                "exact real_name match '%s', single candidate %s" % (name, other)
            )
        else:
            stats["ambiguous"] += 1
            conf, evidence = 0.4, (
                "exact real_name match '%s' but %d candidates: %s"
                % (name, len(cands), ", ".join(cands))
            )
        # CHECK (person_a < person_b) -- the table enforces canonical ordering,
        # so the pair is sorted rather than left in registry-then-github order.
        a, b = sorted((pid, other))
        # Every row is 'proposed'. Nothing here is accepted without a human:
        # confidence carries how sure the match is, status carries whether
        # anyone has agreed to it, and conflating the two is how a 0.9 guess
        # silently becomes a merge.
        claims.append((a, b, "exact_name", conf, evidence, "proposed", now))

    summary = dict(stats)
    summary["registry_unlinked"] = len(registry)
    summary["claims"] = len(claims)
    summary["before"] = before
    summary["applied"] = bool(apply_changes)
    summary["sample"] = [
        {"a": c[0], "b": c[1], "confidence": c[3], "evidence": c[4]}
        for c in claims[:10]
    ]

    if apply_changes:
        # INSERT OR IGNORE does NOT dedupe here: claim_id is an autoincrement
        # PRIMARY KEY, so every row is unique by construction and a re-run
        # doubled the table (6 -> 12) on first test. The CHECK(person_a <
        # person_b) constraint gives canonical ordering but no uniqueness.
        # Skip pairs that already have a claim, and never touch a claim whose
        # status a human has already moved off 'proposed'.
        existing = {
            (a, b) for a, b in g.execute(
                "SELECT person_a, person_b FROM identity_claim"
            )
        }
        fresh = [c for c in claims if (c[0], c[1]) not in existing]
        summary["already_claimed"] = len(claims) - len(fresh)
        g.executemany(
            "INSERT INTO identity_claim "
            "(person_a, person_b, method, confidence, evidence, status, "
            " created_at) VALUES (?,?,?,?,?,?,?)",
            fresh,
        )
        g.commit()
        summary["after"] = {
            "identity_claims": g.execute(
                "SELECT COUNT(*) FROM identity_claim"
            ).fetchone()[0],
            "proposed": g.execute(
                "SELECT COUNT(*) FROM identity_claim WHERE status='proposed'"
            ).fetchone()[0],
        }

    g.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = link(os.path.expanduser(a.graph), a.apply)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
