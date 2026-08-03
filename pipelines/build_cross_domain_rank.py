#!/usr/bin/env python3
"""Build a cross-domain significance score.

WHY THIS EXISTS
---------------
`person.rank_score` is populated for every person, but it is a DIFFERENT UNIT
per domain, so it cannot be compared across them:

    origin |      n | ranked |     max
    github | 245171 | 245171 |  520358   <- summed stars
    books  |  35363 |  35363 |     336   <- work count
    youtube|     48 |     48 |      62
    registry|   140 |      3 |      94

Sorting the graph by rank_score therefore returns 245,171 GitHub accounts before
the first author. "Who are the most significant people here" -- the question a
people graph exists to answer -- is currently unanswerable across domains.

WHAT THIS WRITES
----------------
A `cross_rank` table (NOT a column on person -- see below) holding:

    percentile_in_domain  0-100, this person against their OWN domain
    evidence_breadth      how many independent signals back them
    domain_count          how many domains they appear in
    cross_score           the combined figure

PERCENTILE, NOT NORMALISED RAW VALUE. Star counts are power-law distributed:
scaling them linearly puts torvalds at 100 and everyone else near 0, so the
books population would still lose to GitHub's tail. A percentile asks "how does
this person rank among their peers", which is the only comparison that means the
same thing in both populations.

EVIDENCE BREADTH IS A SEPARATE AXIS, NOT A MULTIPLIER. A person with rated work
AND adoption AND citation AND readable text is better-attested than one with
stars alone, but breadth is a claim about CONFIDENCE, not about significance.
Multiplying them would conflate "we know a lot about them" with "they matter",
so both are stored and cross_score weights them explicitly:

    cross_score = percentile_in_domain * 0.6
                + min(evidence_breadth,5)/5 * 100 * 0.25
                + min(domain_count,3)/3   * 100 * 0.15

The weights are a JUDGEMENT, not a measurement, and they are here in one visible
expression precisely so they can be argued with and changed.

A SEPARATE TABLE, NOT A person COLUMN. person.rank_score is written by the
domain loaders and means "significance within my domain"; overwriting it would
destroy that and break every loader that resumes from it. A derived cross-domain
figure is a different kind of claim and belongs beside the person, not inside
the row -- and it is recomputable from scratch at any time, which a column
mutated in place is not.

Usage:
  build_cross_domain_rank.py --graph people_v2.sqlite [--apply]
"""
import argparse
import json
import sqlite3
import sys
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS cross_rank (
  person_id            TEXT PRIMARY KEY REFERENCES person(person_id) ON DELETE CASCADE,
  origin               TEXT NOT NULL,
  rank_score           REAL,
  percentile_in_domain REAL NOT NULL,
  evidence_breadth     INTEGER NOT NULL,
  domain_count         INTEGER NOT NULL,
  cross_score          REAL NOT NULL,
  built_at             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_cross_score ON cross_rank(cross_score DESC);
CREATE INDEX IF NOT EXISTS ix_cross_origin ON cross_rank(origin, cross_score DESC);
"""

# The signals a person can be backed by, each counted once. json_extract, not
# LIKE -- a LIKE '%value%' also matches repos named "value".
EVIDENCE_KEYS = ("value", "dependent_repos", "list_count", "star_velocity",
                 "legal_lane", "has_text", "text_addressable")


def build(graph_db, apply_changes):
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    before = {}
    try:
        before["cross_rank_rows"] = g.execute(
            "SELECT COUNT(*) FROM cross_rank"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        before["cross_rank_rows"] = 0

    # --- evidence breadth + domain count, one pass over edges ---------------
    breadth, domains = {}, {}
    extract = ", ".join(
        f"json_extract(meta_json,'$.{k}') IS NOT NULL" for k in EVIDENCE_KEYS
    )
    for pid, domain, *flags in g.execute(
        f"SELECT person_id, domain, {extract} FROM person_content"
    ):
        seen = breadth.setdefault(pid, set())
        for k, f in zip(EVIDENCE_KEYS, flags):
            if f:
                seen.add(k)
        d = "youtube" if domain.startswith("youtube") else domain
        domains.setdefault(pid, set()).add(d)

    # --- percentile within each origin -------------------------------------
    people = g.execute(
        "SELECT person_id, origin, COALESCE(rank_score,0) FROM person "
        "WHERE state != 'merged'"
    ).fetchall()

    by_origin = {}
    for pid, origin, score in people:
        by_origin.setdefault(origin, []).append((score, pid))

    # Midpoint-of-tie-block, same as the evidence axis below. GitHub has 69,899
    # people on rank_score 0; spreading them 0..28 by sort order would be pure
    # array-position noise.
    percentile = {}
    for origin, rows in by_origin.items():
        rows.sort()
        n = len(rows)
        i = 0
        while i < n:
            j = i
            while j < n and rows[j][0] == rows[i][0]:
                j += 1
            mid = (i + j - 1) / 2.0
            val = (mid / (n - 1) * 100.0) if n > 1 else 50.0
            for k in range(i, j):
                percentile[rows[k][1]] = val
            i = j

    # Evidence breadth is scored as a PERCENTILE WITHIN THE ORIGIN, for the same
    # reason rank_score is. Two earlier attempts both failed, in opposite
    # directions, and the failures are instructive:
    #
    #   fixed /5 denominator     -> top 1000 was 997 github. Book edges can only
    #                               ever carry 2 of the 5 keys, capping every
    #                               author at 40% of the axis.
    #   /max-achievable-in-origin-> top 1000 was 866 books. 35,216 of 35,363
    #                               book people sit at EXACTLY breadth=2, so the
    #                               axis became a flat +25 domain bonus while
    #                               github's median author earned ~+5.
    #
    # The second is the worse bug: an axis that is constant within a domain is
    # not measuring the person at all. A within-origin percentile is zero when
    # everyone is tied, so a domain with no internal variation contributes
    # nothing here rather than a free bonus -- and github, which does vary,
    # still gets discriminated.
    ev_by_origin = {}
    for pid, origin, _ in people:
        ev_by_origin.setdefault(origin, []).append((len(breadth.get(pid, ())), pid))

    # Ties share the MIDPOINT of their block rather than being spread by array
    # position. With 35,216 book people tied at breadth=2 the ordinal version
    # handed the last of them 100 and the first 0 purely by sort order, which is
    # noise presented as signal. A midpoint gives every tied person the same
    # score -- the honest answer when the axis cannot separate them.
    ev_pct = {}
    for origin, rows in ev_by_origin.items():
        rows.sort()
        n = len(rows)
        i = 0
        while i < n:
            j = i
            while j < n and rows[j][0] == rows[i][0]:
                j += 1
            mid = (i + j - 1) / 2.0
            val = (mid / (n - 1) * 100.0) if n > 1 else 50.0
            for k in range(i, j):
                ev_pct[rows[k][1]] = val
            i = j

    # FOUR ATTEMPTS, and the arithmetic is the lesson. Target is proportional
    # representation -- github holds 87.3% of the graph and books 12.6%, so a
    # sound ranking puts ~873 github / ~126 books in the top 1,000. Neither
    # 1000/0 nor 500/500 is "fair"; proportional is.
    #
    #   v1 breadth / fixed 5            -> 997 github (books capped at 40%)
    #   v2 breadth / max-in-origin      -> 866 BOOKS  (flat +25 domain bonus)
    #   v3 breadth pct, zero when tied  -> 993 github (books axis zeroed)
    #   v4 breadth pct, midpoint ties   -> 997 github (books all share one
    #                                      midpoint; no internal variation to
    #                                      rank on)
    #
    # Every failure traces to the same root: evidence_breadth measures HOW WELL
    # INSTRUMENTED a domain is, not how significant a person is. Books have two
    # possible keys and 35,216 of 35,363 people hold both; the axis is constant
    # there and can only ever act as a domain-level thumb on the scale.
    #
    # So it is no longer part of cross_score. It is still STORED, because "how
    # much do we know about this person" is genuinely useful -- it is just not a
    # component of significance. Ranking now rests on percentile-within-domain,
    # which means the same thing everywhere, plus a small multi-domain bonus for
    # the rare person attested in more than one corpus.
    out = []
    for pid, origin, score in people:
        p = percentile.get(pid, 0.0)
        ev = len(breadth.get(pid, ()))
        dc = len(domains.get(pid, ()))
        cross = p * 0.9 + min(dc, 3) / 3 * 100 * 0.10
        out.append((pid, origin, score, round(p, 3), ev, dc,
                    round(cross, 3), now))

    summary = {
        "people_scored": len(out),
        "origins": {o: len(r) for o, r in by_origin.items()},
        "with_evidence": sum(1 for r in out if r[4] > 0),
        "multi_domain": sum(1 for r in out if r[5] > 1),
        "before": before,
        "applied": bool(apply_changes),
    }

    if apply_changes:
        g.executescript(SCHEMA)
        # Safe to clear: cross_rank is 100% derived from person + person_content
        # by this script and holds no independent data. A percentile is relative
        # to the whole population, so a partial upsert would leave old rows
        # scored against a different denominator -- silently wrong. Nothing that
        # holds source data is ever deleted anywhere in this pipeline.
        g.execute("DELETE FROM cross_rank")
        g.executemany(
            "INSERT INTO cross_rank VALUES (?,?,?,?,?,?,?,?)", out
        )
        g.commit()
        summary["after"] = {
            "cross_rank_rows": g.execute(
                "SELECT COUNT(*) FROM cross_rank"
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
    s = build(a.graph, a.apply)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
