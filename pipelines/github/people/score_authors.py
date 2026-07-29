#!/usr/bin/env python3
r"""Foundry — GitHub AUTHOR/OWNER value model (People layer L2 scoring).

Score and TIER every GitHub owner by a defensible value equation so god-source
orgs (Anthropic, Google, facebookresearch, OpenAI, Microsoft) AND standout
individuals (sindresorhus, karpathy) both surface, ranked god/high/mid/low/shit.

WHY THIS EQUATION (first principles)
====================================
The goal is "who is the most VALUABLE GitHub person/org for a reuse bank?" Value =
(a) do they produce things worth lifting, (b) can they hit a true peak, (c) is the
quality consistent (not a repo farm), (d) is it still alive + legally shippable,
and — as a strong bonus — (e) does the world actually use it. A raw repo count must
NOT win: a mega-org has 1000s of repos but a single great individual (karpathy:
25/42 categorized are saucy) should out-rank a 5000-repo dump-truck.

We score a BASE from SIX core value axes (a weighted average, weights sum to 1.0)
that apply to EVERY owner, then add an ADOPTION BONUS on top:

  base = Σ wᵢ · axisᵢ            (six axes below, each 0-100)
  author_value = clamp( base + ADOPTION_BONUS_MAX · adoption/100 )   ∈ [0,100]

  VOLUME      0.22  log10(saucy + 0.4*v85 + 0.15*categorized) — *value* volume,
                    not repo count. A repo farm scores ~0 here (no saucy/v85).
  PEAK        0.30  max(max_overall_value, max_liftability) blended with
                    log10(top_repo_stars). "Can this owner make ONE great thing?"
                    Heaviest axis — it's what lets a one-hit individual reach god.
  BREADTH     0.13  log-scaled count of distinct categories with a >=70 repo.
                    Rewards range (sindresorhus 45 cats) without letting it dominate.
  DENSITY     0.18  max(saucy/categorized, log10(saucy_abs)). The anti-spam axis.
                    The ratio rewards focused individuals (karpathy 59%); the
                    absolute term rescues high-volume god-sources (microsoft 233
                    saucy = elite capability even at 19% ratio) from being scored
                    as spam. A true spammer (1000 repos, 1% saucy, low abs) stays low.
  FRESHNESS   0.09  recency of most-recent pushed_at (half-life ~2.5yr). Dead orgs
                    decay; still-shipping owners hold value.
  LICENSE     0.08  shippable_ratio = repos with a clean OSI license / total,
                    floored at 30 (missing license metadata ≠ unshippable).

  ADOPTION   (bonus, max +14) log10(max downloads_month) + log10(max dependents)
                    from bank_adoption. Real-world pull = god-source signal. Added
                    on TOP of the base so the covered get lifted and the uncovered
                    (most repos aren't packages) are NEVER penalized to zero.

Design guards:
  * DENSITY uses max(ratio, absolute) so the org-vs-individual tension doesn't cap
    either; both kinds can reach the top via their own strength.
  * Density ratio is gated by a >=4-categorized sample floor (shrink toward 0)
    so a 1-repo-1-saucy owner can't fake 100% density.
  * VOLUME / PEAK / BREADTH / ADOPTION log-scale their power-law inputs (stars,
    downloads, dependents) so a 200k-star repo doesn't swamp every other axis.
  * ADOPTION is additive, not averaged — coverage gaps in bank_adoption (only ~714
    repos resolved) can't sink an Anthropic/karpathy that simply isn't a package.

TIERS — thresholds derived from the ACTUAL score distribution at runtime, not
arbitrary. We compute percentiles over all scored owners and set:
  god  = top tail (>= p99.5 of scored owners that have >=1 categorized repo,
         floor 88) — the handful of true god-sources + standout individuals.
  high = >= p97 (floor 72)
  mid  = >= p90 (floor 55)
  low  = >= p70 (floor 35)
  shit = below that (spam / dead / pure-fork / uncategorized noise).
The runtime prints the chosen cutoffs so they are auditable.

PERFORMANCE — single-scan, two-pass, dict-aggregated (the lesson the prior
people-builder learned the hard way: correlated subqueries HANG on 614k owners).
  Pass A: ONE scan of repo_card  -> per-owner star/fork/license/freshness/top-repo.
  Pass B: ONE scan of repo_category -> per-owner saucy/value/lift/breadth.
  Pass C: ONE scan of bank_adoption -> per-owner max downloads/dependents.
No GROUP BY over 614k owners in SQL, no per-owner re-query. Everything folds into
a python dict keyed by owner in three linear table scans.

I/O CONTRACT
============
  identity.sqlite  : READ-ONLY (opened file:...?mode=ro). Source of all signal.
  people.sqlite    : WRITE. We create/replace ONLY the new `author_value` table
                     and (with --update-graph) set rank_score on existing
                     github-satellite person rows where github_login matches.
                     We never alter identity.sqlite.

Usage (run on the MINI, where the data lives):
  python3 score_authors.py \
      --identity ~/foundry-data/domains/github/identity/identity.sqlite \
      --people   ~/foundry-data/domains/people/people.sqlite \
      --html     "$FOUNDRY_DATA/artifacts/github-author-tiers.html" \
      --update-graph
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

NOW = datetime.now(timezone.utc)
NOW_ISO = NOW.isoformat()

# --- equation weights -------------------------------------------------------
# BASE = weighted average of the SIX core value axes (sum to 1.0). These apply to
# EVERY owner regardless of package coverage, so a god-source is never starved by
# a missing adoption row. Adoption is handled separately as an additive bonus.
W = {
    "volume":    0.22,   # value volume (saucy/v85/categorized), log-scaled
    "peak":      0.30,   # can they make ONE great thing — the individual-god axis
    "breadth":   0.13,   # distinct categories of value
    "density":   0.18,   # saucy/categorized — anti-spam, rewards consistency
    "freshness": 0.09,   # still shipping
    "license":   0.08,   # legally shippable ratio
}
assert abs(sum(W.values()) - 1.0) < 1e-9, W

# ADOPTION is an ADDITIVE BONUS on top of the base, not an averaged axis. Real
# downloads/dependents are a strong POSITIVE signal of god-source status, but most
# repos aren't packages, so the ABSENCE of an adoption row must NOT be a penalty.
# Bonus = ADOPTION_BONUS_MAX * (adoption_axis/100). A fully-adopted owner (sindresorhus,
# 400M dl/mo) gains the full bonus; an uncovered owner gains 0 and keeps its base.
ADOPTION_BONUS_MAX = 14.0

# OSI-ish clean licenses we treat as "shippable" for the license axis.
CLEAN_LICENSES = {
    "mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause", "isc", "mpl-2.0",
    "unlicense", "0bsd", "bsd", "apache", "mpl", "cc0-1.0",
    # weak-copyleft still shippable for most reuse:
    "lgpl-2.1", "lgpl-3.0", "lgpl-2.0",
}
DENSITY_FLOOR = 4   # need >=4 categorized repos before density counts


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def log_norm(x, scale):
    """log10-normalize a power-law value to ~0..100 via a scale factor."""
    if not x or x <= 0:
        return 0.0
    return min(100.0, math.log10(x + 1) * scale)


def years_since(iso_ts: str) -> float:
    if not iso_ts:
        return 99.0
    s = iso_ts.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # fall back: try date-only
        try:
            dt = datetime.fromisoformat(s[:10]).replace(tzinfo=timezone.utc)
        except ValueError:
            return 99.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (NOW - dt).total_seconds() / (365.25 * 86400))


# --------------------------------------------------------------------------- #
# Aggregation: three single-table scans into one dict keyed by owner.
# --------------------------------------------------------------------------- #
def aggregate(identity: Path):
    ro = sqlite3.connect(f"file:{identity}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row
    owners: dict[str, dict] = {}

    def blank(o):
        return {
            "owner": o,
            # volume / structure
            "n_repos": 0, "n_active": 0,
            # stars / fame
            "total_stars": 0, "max_stars": 0,
            "top_repo": None, "_top_stars": -1,
            # license
            "n_clean": 0,
            # freshness
            "latest_push": "",
            # category-derived (pass B)
            "n_cat": 0, "saucy_cnt": 0, "v85": 0,
            "max_ov": 0, "max_lift": 0,
            "_cats70": set(),
            # adoption (pass C)
            "adopt_dl": 0, "adopt_dep": 0,
        }

    # ---- Pass A: repo_card (one scan) ----
    t0 = time.time()
    nA = 0
    for rc in ro.execute(
        "SELECT substr(full_name,1,instr(full_name,'/')-1) AS owner, full_name, "
        "stars, license, pushed_at, archived, fork "
        "FROM repo_card WHERE full_name LIKE '%/%'"
    ):
        o = rc["owner"]
        if not o:
            continue
        d = owners.get(o)
        if d is None:
            d = owners[o] = blank(o)
        st = rc["stars"] or 0
        d["n_repos"] += 1
        d["total_stars"] += st
        if st > d["max_stars"]:
            d["max_stars"] = st
        if st > d["_top_stars"]:
            d["_top_stars"] = st
            d["top_repo"] = rc["full_name"]
        lic = (rc["license"] or "").strip().lower()
        if lic in CLEAN_LICENSES:
            d["n_clean"] += 1
        if not rc["archived"]:
            d["n_active"] += 1
        pa = rc["pushed_at"] or ""
        if pa > d["latest_push"]:
            d["latest_push"] = pa
        nA += 1
    tA = time.time() - t0

    # ---- Pass B: repo_category (one scan) ----
    t0 = time.time()
    nB = 0
    for cat in ro.execute(
        "SELECT substr(full_name,1,instr(full_name,'/')-1) AS owner, "
        "saucy, overall_value, liftability, category_id "
        "FROM repo_category WHERE full_name LIKE '%/%'"
    ):
        d = owners.get(cat["owner"])
        if d is None:
            continue  # categorized repo whose owner had no repo_card (rare) — skip
        d["n_cat"] += 1
        d["saucy_cnt"] += (cat["saucy"] or 0)
        ov = cat["overall_value"] or 0
        if ov >= 85:
            d["v85"] += 1
        if ov > d["max_ov"]:
            d["max_ov"] = ov
        lf = cat["liftability"] or 0
        if lf > d["max_lift"]:
            d["max_lift"] = lf
        if ov >= 70 and cat["category_id"]:
            d["_cats70"].add(cat["category_id"])
        nB += 1
    tB = time.time() - t0

    # ---- Pass C: bank_adoption (one scan) ----
    t0 = time.time()
    nC = 0
    for ad in ro.execute(
        "SELECT substr(full_name,1,instr(full_name,'/')-1) AS owner, "
        "downloads_month, downloads_total, dependents "
        "FROM bank_adoption WHERE full_name LIKE '%/%'"
    ):
        d = owners.get(ad["owner"])
        if d is None:
            continue
        dl = max(ad["downloads_month"] or 0, ad["downloads_total"] or 0)
        if dl > d["adopt_dl"]:
            d["adopt_dl"] = dl
        dep = ad["dependents"] or 0
        if dep > d["adopt_dep"]:
            d["adopt_dep"] = dep
        nC += 1
    tC = time.time() - t0

    ro.close()
    print(f"[aggregate] repo_card rows={nA} ({tA:.1f}s)  "
          f"repo_category rows={nB} ({tB:.1f}s)  "
          f"bank_adoption rows={nC} ({tC:.1f}s)  owners={len(owners)}")
    return owners


# --------------------------------------------------------------------------- #
# Scoring: turn aggregates into 7 axes + composite.
# --------------------------------------------------------------------------- #
def score_owner(d: dict) -> dict:
    n_cat = d["n_cat"]
    saucy = d["saucy_cnt"]

    # VOLUME — value volume, log-scaled. saucy weighted highest, then v85, then cat.
    vol_raw = saucy + 0.4 * d["v85"] + 0.15 * n_cat
    a_volume = log_norm(vol_raw, scale=52.0)   # ~50 value-units -> ~89; god-source
    #                                            orgs (200+ saucy) pin near 100.

    # PEAK — best single thing. blend best categorized value/lift with star fame.
    # Heaviest axis: this is what lets a one-hit individual (karpathy, torvalds)
    # reach the top. peak_quality from the categorizer, peak_fame from star mass.
    peak_quality = max(d["max_ov"], d["max_lift"])           # 0..~95
    peak_fame = log_norm(d["max_stars"], scale=20.0)         # 100k stars -> ~100
    a_peak = clamp(0.55 * peak_quality + 0.45 * peak_fame)

    # BREADTH — distinct >=70 categories, log-scaled.
    a_breadth = log_norm(len(d["_cats70"]), scale=64.0)      # ~30 cats -> ~95

    # ADOPTION — real downloads + dependents, log-scaled, blended. Used ONLY as an
    # additive bonus downstream (not in the averaged base), so a missing row = 0
    # bonus, never a penalty.
    adl = log_norm(d["adopt_dl"], scale=11.0)                # 1e9 dl -> ~99
    adep = log_norm(d["adopt_dep"], scale=15.0)              # 1e6 dep -> ~90
    a_adoption = clamp(0.6 * adl + 0.4 * adep)

    # DENSITY — quality consistency. Two failure modes to avoid:
    #   (a) spammer with 1000 repos and 1% saucy -> must score LOW (ratio handles this)
    #   (b) god-source ORG with 1195 repos / 233 saucy (19% ratio) -> must NOT be
    #       scored as spam, because 233 saucy in absolute is elite capability.
    # So density = max(ratio_density, absolute_density), each gated by sample floor.
    # ratio rewards focused individuals; absolute rescues high-volume god-sources.
    if n_cat >= DENSITY_FLOOR:
        ratio_density = clamp(saucy / n_cat * 100.0)
        abs_density = log_norm(saucy, scale=42.0)            # 100 saucy -> ~84
        a_density = max(ratio_density, abs_density)
    elif n_cat > 0:
        # small sample: shrink ratio toward 0 prior (can't fake density on 1 repo)
        a_density = clamp(saucy / n_cat * 100.0) * (n_cat / DENSITY_FLOOR)
    else:
        a_density = 0.0

    # FRESHNESS — 2.5yr half-life decay on most-recent push.
    yrs = years_since(d["latest_push"])
    a_freshness = clamp(100.0 * (0.5 ** (yrs / 2.5)))

    # LICENSE — clean / total. Research orgs (facebookresearch) often lack standard
    # license metadata; floor the contribution so it can't alone sink a god-source.
    a_license = clamp(d["n_clean"] / d["n_repos"] * 100.0) if d["n_repos"] else 0.0
    a_license = max(a_license, 30.0)   # neutral prior: unknown license != unshippable

    axes = {
        "volume": a_volume, "peak": a_peak, "breadth": a_breadth,
        "adoption": a_adoption, "density": a_density,
        "freshness": a_freshness, "license": a_license,
    }
    # BASE = weighted average of the six core axes (W sums to 1.0).
    base = sum(W[k] * axes[k] for k in W)
    # ADOPTION BONUS = additive lift, 0..ADOPTION_BONUS_MAX, never a penalty.
    bonus = ADOPTION_BONUS_MAX * (a_adoption / 100.0)
    composite = clamp(base + bonus)
    return axes, composite


# --------------------------------------------------------------------------- #
# Tier thresholds from the ACTUAL distribution (over owners w/ >=1 categorized).
# --------------------------------------------------------------------------- #
def derive_tiers(scored: list[dict]):
    cat_scores = sorted(s["score"] for s in scored if s["n_cat"] >= 1)
    n = len(cat_scores)

    def pct(p):
        if n == 0:
            return 0.0
        i = min(n - 1, int(p * n))
        return cat_scores[i]

    cut = {
        "god":  max(88.0, pct(0.995)),
        "high": max(72.0, pct(0.97)),
        "mid":  max(55.0, pct(0.90)),
        "low":  max(35.0, pct(0.70)),
    }
    # keep monotonic
    cut["high"] = min(cut["high"], cut["god"] - 0.01)
    cut["mid"] = min(cut["mid"], cut["high"] - 0.01)
    cut["low"] = min(cut["low"], cut["mid"] - 0.01)
    return cut, n


def tier_of(score, n_cat, cut):
    if n_cat == 0:
        return "shit"   # uncategorized noise can't be ranked above low
    if score >= cut["god"]:
        return "god"
    if score >= cut["high"]:
        return "high"
    if score >= cut["mid"]:
        return "mid"
    if score >= cut["low"]:
        return "low"
    return "shit"


# --------------------------------------------------------------------------- #
# Persistence: write author_value table into people.sqlite.
# --------------------------------------------------------------------------- #
def write_table(people: Path, rows: list[dict]):
    con = sqlite3.connect(str(people))
    con.execute("DROP TABLE IF EXISTS author_value")
    con.execute("""
        CREATE TABLE author_value (
            owner          TEXT PRIMARY KEY,
            score          REAL NOT NULL,
            tier           TEXT NOT NULL,
            s_volume       REAL, s_peak REAL, s_breadth REAL, s_adoption REAL,
            s_density      REAL, s_freshness REAL, s_license REAL,
            repo_count     INTEGER,
            cat_count      INTEGER,
            saucy_count    INTEGER,
            v85_count      INTEGER,
            breadth_cats   INTEGER,
            top_repo       TEXT,
            top_repo_stars INTEGER,
            total_stars    INTEGER,
            max_overall    INTEGER,
            max_lift       INTEGER,
            adoption_max   INTEGER,
            dependents_max INTEGER,
            latest_push    TEXT,
            kind           TEXT,          -- 'org' | 'individual' heuristic
            built_at       TEXT
        )
    """)
    con.executemany("""
        INSERT INTO author_value VALUES
        (:owner,:score,:tier,:s_volume,:s_peak,:s_breadth,:s_adoption,:s_density,
         :s_freshness,:s_license,:repo_count,:cat_count,:saucy_count,:v85_count,
         :breadth_cats,:top_repo,:top_repo_stars,:total_stars,:max_overall,
         :max_lift,:adoption_max,:dependents_max,:latest_push,:kind,:built_at)
    """, rows)
    con.execute("CREATE INDEX idx_av_tier ON author_value(tier)")
    con.execute("CREATE INDEX idx_av_score ON author_value(score DESC)")
    con.commit()
    con.close()


# --------------------------------------------------------------------------- #
# Graph update: set rank_score on existing github-satellite people.
# --------------------------------------------------------------------------- #
def update_graph(people: Path, score_by_owner: dict[str, dict]):
    con = sqlite3.connect(str(people))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT person_id, value FROM external_ids WHERE platform='github_login'"
    ).fetchall()
    updated, matched = 0, 0
    for r in rows:
        login = r["value"]
        s = score_by_owner.get(login) or score_by_owner.get(login.lower())
        if not s:
            continue
        matched += 1
        con.execute(
            "UPDATE person SET rank_score=?, primary_tier=COALESCE(primary_tier, ?) "
            "WHERE person_id=?",
            (round(s["score"], 2), s["tier"], r["person_id"]),
        )
        # also stamp the author_value into the github person_content meta for that owner
        pc = con.execute(
            "SELECT content_ref, meta_json FROM person_content "
            "WHERE person_id=? AND domain='github'", (r["person_id"],)
        ).fetchall()
        for c in pc:
            try:
                meta = json.loads(c["meta_json"] or "{}")
            except Exception:
                meta = {}
            meta["author_value"] = round(s["score"], 2)
            meta["author_tier"] = s["tier"]
            con.execute(
                "UPDATE person_content SET meta_json=? "
                "WHERE person_id=? AND domain='github' AND content_ref=?",
                (json.dumps(meta), r["person_id"], c["content_ref"]),
            )
        updated += 1
    con.commit()
    con.close()
    print(f"[graph] github_login rows={len(rows)} matched={matched} updated={updated}")
    return updated


# --------------------------------------------------------------------------- #
def kind_of(d: dict) -> str:
    """Heuristic org-vs-individual. Orgs tend to have many repos AND a known
    org-shape login. Not load-bearing for scoring; purely a visible label."""
    if d["n_repos"] >= 60:
        return "org"
    return "individual"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--identity", required=True, type=Path)
    ap.add_argument("--people", required=True, type=Path)
    ap.add_argument("--html", required=True, type=Path)
    ap.add_argument("--update-graph", action="store_true")
    ap.add_argument("--min-cat", type=int, default=1,
                    help="only TABLE-write owners with >= this many categorized "
                         "repos (keeps author_value to ranked owners, not 614k noise). "
                         "0 = write everyone.")
    args = ap.parse_args()

    owners = aggregate(args.identity)

    # score everyone
    scored = []
    for o, d in owners.items():
        axes, composite = score_owner(d)
        scored.append({
            "owner": o, "score": composite, "axes": axes,
            "n_repos": d["n_repos"], "n_cat": d["n_cat"],
            "saucy": d["saucy_cnt"], "v85": d["v85"],
            "breadth": len(d["_cats70"]),
            "top_repo": d["top_repo"], "top_stars": max(d["max_stars"], 0),
            "total_stars": d["total_stars"], "max_ov": d["max_ov"],
            "max_lift": d["max_lift"], "adopt_dl": d["adopt_dl"],
            "adopt_dep": d["adopt_dep"], "latest_push": d["latest_push"],
            "kind": kind_of(d),
        })

    cut, n_cat_pop = derive_tiers(scored)
    for s in scored:
        s["tier"] = tier_of(s["score"], s["n_cat"], cut)

    print("\n=== TIER CUTOFFS (derived from distribution) ===")
    print(json.dumps({k: round(v, 2) for k, v in cut.items()}, indent=2))
    print(f"(population for percentiles = {n_cat_pop} owners with >=1 categorized repo)")

    # tier distribution
    from collections import Counter
    dist = Counter(s["tier"] for s in scored)
    print("\n=== TIER DISTRIBUTION (all owners) ===")
    for t in ["god", "high", "mid", "low", "shit"]:
        print(f"  {t:5s}: {dist.get(t,0)}")

    # build score-by-owner index for table + graph
    score_by_owner = {s["owner"]: s for s in scored}

    # rows to write: owners with >= min-cat categorized repos
    table_rows = []
    for s in scored:
        if s["n_cat"] < args.min_cat:
            continue
        a = s["axes"]
        table_rows.append({
            "owner": s["owner"], "score": round(s["score"], 2), "tier": s["tier"],
            "s_volume": round(a["volume"], 1), "s_peak": round(a["peak"], 1),
            "s_breadth": round(a["breadth"], 1), "s_adoption": round(a["adoption"], 1),
            "s_density": round(a["density"], 1), "s_freshness": round(a["freshness"], 1),
            "s_license": round(a["license"], 1),
            "repo_count": s["n_repos"], "cat_count": s["n_cat"],
            "saucy_count": s["saucy"], "v85_count": s["v85"],
            "breadth_cats": s["breadth"], "top_repo": s["top_repo"],
            "top_repo_stars": s["top_stars"], "total_stars": s["total_stars"],
            "max_overall": s["max_ov"], "max_lift": s["max_lift"],
            "adoption_max": s["adopt_dl"], "dependents_max": s["adopt_dep"],
            "latest_push": s["latest_push"], "kind": s["kind"],
            "built_at": NOW_ISO,
        })
    write_table(args.people, table_rows)
    print(f"\n[table] wrote author_value: {len(table_rows)} owners "
          f"(>= {args.min_cat} categorized) -> {args.people}")

    if args.update_graph:
        update_graph(args.people, score_by_owner)

    # ---- emit HTML ----
    emit_html(args.html, scored, cut, dist, n_cat_pop)
    print(f"[html] wrote {args.html}")

    # ---- PROOF: god-tier + known-name spot checks ----
    print("\n=== GOD-TIER (top 30 by score) ===")
    god = sorted([s for s in scored if s["tier"] == "god"],
                 key=lambda s: -s["score"])[:30]
    for s in god:
        a = s["axes"]
        print(f"  {s['score']:5.1f} {s['kind']:10s} {s['owner']:24s} "
              f"V{a['volume']:.0f} P{a['peak']:.0f} B{a['breadth']:.0f} "
              f"A{a['adoption']:.0f} D{a['density']:.0f} F{a['freshness']:.0f} "
              f"L{a['license']:.0f} | saucy={s['saucy']}/{s['n_cat']} "
              f"top={s['top_repo']}({s['top_stars']}*)")

    print("\n=== KNOWN-NAME SPOT CHECKS ===")
    for o in ["anthropics", "google", "facebookresearch", "openai", "microsoft",
              "sindresorhus", "karpathy", "huggingface", "vercel", "meta-llama",
              "torvalds", "tensorflow", "pytorch", "langchain-ai"]:
        s = score_by_owner.get(o)
        if not s:
            print(f"  {o:20s}: (not in data)")
            continue
        print(f"  {o:20s}: {s['score']:5.1f} [{s['tier']:4s}] "
              f"repos={s['n_repos']} cat={s['n_cat']} saucy={s['saucy']} "
              f"top={s['top_repo']}")


# --------------------------------------------------------------------------- #
# HTML emitter — browsable ranked author tiers.
# --------------------------------------------------------------------------- #
def emit_html(path: Path, scored, cut, dist, n_cat_pop):
    tiers = ["god", "high", "mid", "low"]   # 'shit' omitted from the browsable list
    by_tier = {t: sorted([s for s in scored if s["tier"] == t],
                         key=lambda s: -s["score"]) for t in tiers}

    def axis_bar(label, v):
        v = max(0, min(100, v))
        hue = int(v * 1.2)  # 0=red -> 120=green
        return (f'<div class="ax"><span class="axl">{label}</span>'
                f'<span class="axt" style="width:{v:.0f}%;background:hsl({hue},65%,45%)"></span>'
                f'<span class="axv">{v:.0f}</span></div>')

    TIER_META = {
        "god":  ("#ffd23f", "GOD", "Top tail. Anthropic / Google / Meta-research / "
                                   "OpenAI / Microsoft class orgs + standout individuals."),
        "high": ("#7ee787", "HIGH", "Heavy hitters — strong on most axes."),
        "mid":  ("#79c0ff", "MID", "Solid, focused producers of reusable value."),
        "low":  ("#8b949e", "LOW", "Some categorized value; thin or aging."),
    }

    def card(s):
        a = s["axes"]
        adopt = ""
        if s["adopt_dl"] or s["adopt_dep"]:
            adopt = (f'<span class="badge adopt">adoption: '
                     f'{s["adopt_dl"]:,} dl/mo · {s["adopt_dep"]:,} deps</span>')
        return f"""
      <div class="card" data-owner="{s['owner']}" data-score="{s['score']:.1f}" data-kind="{s['kind']}">
        <div class="chead">
          <a class="owner" href="https://github.com/{s['owner']}" target="_blank">{s['owner']}</a>
          <span class="kind {s['kind']}">{s['kind']}</span>
          <span class="score">{s['score']:.1f}</span>
        </div>
        <div class="meta">
          {s['saucy']} saucy / {s['n_cat']} categorized ({s['n_repos']} repos) ·
          {s['v85']}×85+ · {s['breadth']} categories
          {adopt}
        </div>
        <div class="top">top: <a href="https://github.com/{s['top_repo']}" target="_blank">{s['top_repo'] or '—'}</a>
          <span class="stars">{s['top_stars']:,}★</span></div>
        <div class="axes">
          {axis_bar('volume', a['volume'])}{axis_bar('peak', a['peak'])}
          {axis_bar('breadth', a['breadth'])}{axis_bar('adoption', a['adoption'])}
          {axis_bar('density', a['density'])}{axis_bar('fresh', a['freshness'])}
          {axis_bar('license', a['license'])}
        </div>
      </div>"""

    sections = []
    for t in tiers:
        col, lbl, desc = TIER_META[t]
        cards = "".join(card(s) for s in by_tier[t][:200])  # cap mid/low lists
        more = (f'<p class="more">… and {len(by_tier[t]) - 200} more in this tier '
                f'(see author_value table)</p>' if len(by_tier[t]) > 200 else "")
        sections.append(f"""
    <section class="tier" id="tier-{t}">
      <h2 style="border-color:{col}"><span class="tdot" style="background:{col}"></span>
        {lbl} TIER <span class="tcount">{len(by_tier[t])}</span></h2>
      <p class="tdesc">{desc} &nbsp;·&nbsp; cutoff ≥ {cut.get(t, 0):.1f}</p>
      <div class="grid">{cards}</div>{more}
    </section>""")

    cuts_html = " · ".join(f"{k} ≥ {v:.1f}" for k, v in cut.items())
    dist_html = " · ".join(f"{t}: {dist.get(t,0):,}" for t in ['god','high','mid','low','shit'])

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Foundry — GitHub Author Value Tiers (L2 People scoring)</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    margin:0; background:#0d1117; color:#c9d1d9; }}
  header {{ padding:24px 28px; border-bottom:1px solid #21262d; background:#010409;
    position:sticky; top:0; z-index:10; }}
  h1 {{ margin:0 0 6px; font-size:21px; }}
  .sub {{ color:#8b949e; font-size:12.5px; }}
  .eq {{ margin-top:10px; font-size:12px; color:#8b949e; max-width:1100px; }}
  .eq code {{ color:#79c0ff; }}
  nav {{ margin-top:12px; }}
  nav a {{ color:#c9d1d9; text-decoration:none; margin-right:14px; font-weight:600;
    padding:4px 10px; border:1px solid #30363d; border-radius:6px; font-size:12.5px; }}
  nav a:hover {{ background:#161b22; }}
  .filter {{ margin-top:12px; }}
  .filter input, .filter select {{ background:#0d1117; color:#c9d1d9;
    border:1px solid #30363d; border-radius:6px; padding:6px 10px; font-size:13px; }}
  main {{ padding:20px 28px 80px; max-width:1500px; }}
  section.tier {{ margin-bottom:40px; }}
  h2 {{ font-size:18px; border-left:4px solid; padding-left:10px; margin:24px 0 4px;
    display:flex; align-items:center; gap:8px; }}
  .tdot {{ width:12px;height:12px;border-radius:50%; display:inline-block; }}
  .tcount {{ font-size:13px; color:#8b949e; font-weight:400; }}
  .tdesc {{ color:#8b949e; font-size:12.5px; margin:0 0 14px 14px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr));
    gap:12px; }}
  .card {{ background:#161b22; border:1px solid #21262d; border-radius:10px;
    padding:12px 14px; }}
  .card:hover {{ border-color:#388bfd; }}
  .chead {{ display:flex; align-items:center; gap:8px; margin-bottom:4px; }}
  .owner {{ font-weight:700; font-size:15px; color:#58a6ff; text-decoration:none; }}
  .owner:hover {{ text-decoration:underline; }}
  .kind {{ font-size:10px; text-transform:uppercase; padding:1px 6px; border-radius:10px;
    letter-spacing:.5px; }}
  .kind.org {{ background:#1f6feb33; color:#79c0ff; }}
  .kind.individual {{ background:#23863633; color:#7ee787; }}
  .score {{ margin-left:auto; font-weight:800; font-size:17px; }}
  .meta {{ color:#8b949e; font-size:11.5px; margin-bottom:3px; }}
  .badge.adopt {{ display:inline-block; margin-left:6px; color:#ffd23f; }}
  .top {{ font-size:12px; margin-bottom:8px; }}
  .top a {{ color:#a5d6ff; text-decoration:none; }}
  .stars {{ color:#8b949e; }}
  .axes {{ display:grid; grid-template-columns:1fr 1fr; gap:2px 12px; }}
  .ax {{ display:flex; align-items:center; gap:6px; font-size:10px; }}
  .axl {{ width:48px; color:#8b949e; text-align:right; }}
  .axt {{ height:7px; border-radius:4px; display:inline-block; min-width:1px; }}
  .axv {{ width:20px; color:#8b949e; }}
  .more {{ color:#8b949e; font-size:12px; margin-left:14px; }}
</style></head>
<body>
<header>
  <h1>Foundry — GitHub Author Value Tiers</h1>
  <div class="sub">L2 People-layer owner scoring · {n_cat_pop:,} owners with categorized
    repos scored · built {NOW.strftime('%Y-%m-%d %H:%M UTC')}</div>
  <div class="eq">value = 100·Σ wᵢ·axisᵢ &nbsp;—&nbsp;
    <code>volume .18</code> <code>peak .22</code> <code>breadth .10</code>
    <code>adoption .20</code> <code>density .15</code> <code>fresh .08</code>
    <code>license .07</code> · cutoffs: {cuts_html} · dist: {dist_html}</div>
  <nav>
    <a href="#tier-god">GOD</a><a href="#tier-high">HIGH</a>
    <a href="#tier-mid">MID</a><a href="#tier-low">LOW</a>
  </nav>
  <div class="filter">
    <input id="q" placeholder="filter owner…" oninput="filt()">
    <select id="kind" onchange="filt()">
      <option value="">all</option><option value="org">orgs</option>
      <option value="individual">individuals</option>
    </select>
  </div>
</header>
<main>{''.join(sections)}</main>
<script>
function filt(){{
  var q=document.getElementById('q').value.toLowerCase();
  var k=document.getElementById('kind').value;
  document.querySelectorAll('.card').forEach(function(c){{
    var okq=!q||c.dataset.owner.toLowerCase().indexOf(q)>=0;
    var okk=!k||c.dataset.kind===k;
    c.style.display=(okq&&okk)?'':'none';
  }});
}}
</script>
</body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html)


if __name__ == "__main__":
    main()
