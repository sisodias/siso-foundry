#!/usr/bin/env python3
"""
Foundry Bank API  (wild3)
=========================
The queryable interface an app-builder / agent calls:

    need(capability) -> ranked liftable cards + repos + SELECT-value steering

The bank's proven value is SELECT (steering you to the right library OFFLINE,
with the gotchas baked in) -- not WIRE. So every result carries the steering:
one-liner, legal lane, provides/requires, the dangerous gotchas, the smoke check.

Rankings are grounded in LIFTABILITY + ADOPTION (real downloads / dependent repos),
NOT fame (stars). A fame-trap correction demotes high-star / low-real-adoption repos.

Data (read-only here): identity.sqlite
  bank_contractcard    -- 20 deep-extracted gold cards (4-layer, gotchas)  = the steering
  bank_repo            -- 23,778 capability-tagged candidates              = the breadth
  bank_capability_tag  -- 104 frozen-vocab capability tags                 = the need() input
  bank_tag_crosswalk   -- seed-tag -> canonical registry capability
  bank_adoption_v2     -- real download / dependent-repo adoption signal
  bank_liftable_ranked -- fame-trap-corrected liftability per repo

Writes (idempotent): bank_query_resolution  -- logs each need() resolution for audit.

Usage:
    python3 bank.py need <capability> [--limit N] [--json]
    python3 bank.py caps [--domain D]          # list the 104-tag vocab
    python3 bank.py card <card_id>             # full steering for one card
"""
import sqlite3, json, sys, argparse, difflib, datetime, textwrap, os
from pathlib import Path

DB = os.environ.get(
    "FOUNDRY_GITHUB_DB",
    str(Path.home() / ".local" / "share" / "siso-foundry" / "domains" / "github" / "identity" / "identity.sqlite"),
)

# ---- capability resolver -------------------------------------------------
# The need() input is a 104-frozen-vocab tag (e.g. http-client, jwt-auth,
# vector-search). Three internal vocabularies must be bridged:
#   (a) card BAND          (10 bands: http, crypto, vector-search, ...)
#   (b) repo SEED TAG      (29: http-client, auth-sdk, ...)  via reverse crosswalk
#   (c) liftable CAT SLUG  (vector-search-library, http-networking-client, ...)
# This map encodes the bridge for the common capabilities; anything unmapped
# falls back to fuzzy matching the capability string against repo tags + cat slugs.
CAP_BRIDGE = {
    "http-client":   {"bands": ["http"],          "seed": ["http-client"],                 "cats": ["http-networking-client"]},
    "jwt-auth":      {"bands": ["crypto"],         "seed": ["auth-sdk"],                    "cats": ["client-library-sdk"],
                      "card_filter": "jwt"},  # within crypto band, prefer JWT-providing cards
    "vector-search": {"bands": ["vector-search"],  "seed": ["search-client"],               "cats": ["vector-search-library"]},
    "graphql-client":{"bands": [],                 "seed": ["graphql-client"],              "cats": ["http-networking-client"]},
    "websocket":     {"bands": [],                 "seed": ["websocket-client"],            "cats": ["http-networking-client"]},
    "orm":           {"bands": ["data-access"],    "seed": ["orm", "db-driver", "db-client"], "cats": ["client-library-sdk"]},
    "validation":    {"bands": ["validation"],     "seed": ["validation"],                  "cats": ["client-library-sdk"]},
    "json-parse":    {"bands": ["parse"],          "seed": ["serialization"],               "cats": ["client-library-sdk"]},
    "cli-builder":   {"bands": ["cli"],            "seed": ["cli-builder"],                 "cats": ["cli-utility"]},
    "crypto-signing":{"bands": ["crypto"],         "seed": ["crypto-primitive"],            "cats": ["client-library-sdk"]},
}


def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def ensure_log_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS bank_query_resolution (
            query        TEXT,
            resolved_cap TEXT,
            n_cards      INTEGER,
            n_repos      INTEGER,
            top_pick     TEXT,
            resolved_at  TEXT DEFAULT (datetime('now'))
        )""")
    con.commit()


def resolve_capability(con, cap):
    """Map a free-text need() to a known capability + its bridge.
    Returns (resolved_cap, bridge_dict, how)."""
    cap = cap.strip().lower()
    # 1. exact frozen-vocab tag
    row = con.execute("SELECT tag FROM bank_capability_tag WHERE tag=?", (cap,)).fetchone()
    if cap in CAP_BRIDGE:
        return cap, CAP_BRIDGE[cap], "bridge-exact"
    if row:
        # known vocab tag but no hand-bridge -> derive a fuzzy bridge
        return cap, _fuzzy_bridge(cap), "vocab-fuzzy"
    # 2. fuzzy against the 104 vocab
    vocab = [r["tag"] for r in con.execute("SELECT tag FROM bank_capability_tag")]
    near = difflib.get_close_matches(cap, vocab, n=1, cutoff=0.55)
    if near:
        t = near[0]
        return t, CAP_BRIDGE.get(t, _fuzzy_bridge(t)), f"fuzzy->{t}"
    # 3. last resort: treat the string itself as a keyword bridge
    return cap, _fuzzy_bridge(cap), "keyword-only"


def _fuzzy_bridge(cap):
    base = cap.split("-")[0]
    return {"bands": [], "seed": [], "cats": [], "keyword": base}


def _adoption_norm(row):
    """0..100 real-adoption signal, fame-corrected. Prefers real download/dependent
    signal (adoption_v2.real_value) over stars."""
    if row and row["real_value"] is not None:
        return float(row["real_value"]), "real-adoption"
    if row and row["adoption_score"] is not None:
        return float(row["adoption_score"]), "adoption-score"
    return None, "no-adoption-data"


def gather_cards(con, cap, bridge, limit):
    """Pull the deep-extracted gold cards that match the capability. These carry
    the SELECT-value steering (gotchas, legal lane, provides/requires)."""
    bands = bridge.get("bands") or []
    out = []
    seen = set()
    q_bands = bands if bands else []
    # band-matched cards
    if q_bands:
        ph = ",".join("?" * len(q_bands))
        rows = con.execute(f"SELECT * FROM bank_contractcard WHERE band IN ({ph})", q_bands).fetchall()
    else:
        rows = con.execute("SELECT * FROM bank_contractcard").fetchall()
    cfilter = bridge.get("card_filter")
    for c in rows:
        if c["card_id"] in seen:
            continue
        blob = " ".join(str(c[k] or "") for k in ("one_liner", "provides", "display_name", "card_id")).lower()
        if cfilter and cfilter not in blob:
            continue
        if not q_bands:
            # no band bridge -> keyword gate against the card text
            kw = bridge.get("keyword") or cap.split("-")[0]
            if kw and kw not in blob:
                continue
        seen.add(c["card_id"])
        ad = con.execute("SELECT real_value, adoption_score FROM bank_adoption_v2 WHERE full_name=?", (c["full_name"],)).fetchone()
        adv, adsrc = _adoption_norm(ad)
        lift = c["liftability"] or 0
        # select_score: liftability dominates (it's the lift judgment), adoption
        # confirms real use. Cards get +5 because they carry steering you can't get
        # from a raw repo row.
        score = lift + (adv if adv is not None else 50) * 0.5 + 5
        out.append({
            "kind": "card",
            "card_id": c["card_id"],
            "full_name": c["full_name"],
            "one_liner": c["one_liner"],
            "band": c["band"],
            "language": c["language"],
            "license": c["license"],
            "legal_lane": c["legal_lane"],
            "liftability": lift,
            "adoption": adv,
            "adoption_src": adsrc,
            "select_score": round(score, 1),
            "provides": _json(c["provides"]),
            "requires": _json(c["requires"]),
            "assumptions": _json(c["assumptions"]),
            "smoke": c["smoke"],
            "surface": c["surface"],
            "gotchas": _top_gotchas(c["semantics"]),
        })
    out.sort(key=lambda x: x["select_score"], reverse=True)
    return out[:limit]


def gather_repos(con, cap, bridge, limit, exclude):
    """Broader candidate repos for the capability, ranked by liftability+adoption."""
    seed = bridge.get("seed") or []
    cats = bridge.get("cats") or []
    kw = bridge.get("keyword") or cap.split("-")[0]
    # generic catch-all cats carry the whole utility long-tail; they are NOT
    # capability-faithful on their own, so we only trust them when keyword-gated.
    GENERIC_CATS = {"client-library-sdk", "general-utility-helpers", "dev-tools", "cli-utility"}
    rows = {}
    # path A: repo capability_tag matches a seed tag  -- the strongest signal
    if seed:
        ph = ",".join("?" * len(seed))
        for r in con.execute(f"SELECT full_name, capability_tag, reuse_value, stars, language, license, one_line, description FROM bank_repo WHERE capability_tag IN ({ph})", seed):
            rows[r["full_name"]] = dict(r)
    # path B: liftable_ranked SPECIFIC categories (e.g. vector-search-library) -- trustworthy.
    #         generic cats are keyword-gated so the utility long-tail can't leak in.
    if cats:
        ph = ",".join("?" * len(cats))
        for r in con.execute(f"SELECT full_name, liftability, reuse_value, stars, language, license, description, cat_slug FROM bank_liftable_ranked WHERE cat_slug IN ({ph})", cats):
            if r["cat_slug"] in GENERIC_CATS:
                blob = f"{r['full_name']} {r['description'] or ''}".lower()
                if kw not in blob:
                    continue  # generic cat row must mention the capability keyword
            d = dict(r)
            rows.setdefault(r["full_name"], d)
            rows[r["full_name"]].setdefault("liftability", r["liftability"])
    # path C: keyword fallback over descriptions/names -- ONLY when the faithful
    #         paths produced nothing (unmapped caps). Always keyword-gated.
    if not rows:
        like = f"%{kw}%"
        for r in con.execute(
            "SELECT full_name, capability_tag, reuse_value, stars, language, license, one_line, description "
            "FROM bank_repo WHERE lower(description) LIKE ? OR lower(full_name) LIKE ? OR lower(one_line) LIKE ? LIMIT 200",
            (like, like, like)):
            rows.setdefault(r["full_name"], dict(r))

    out = []
    for fn, r in rows.items():
        if fn in exclude:
            continue
        ad = con.execute("SELECT real_value, adoption_score FROM bank_adoption_v2 WHERE full_name=?", (fn,)).fetchone()
        adv, adsrc = _adoption_norm(ad)
        lr = con.execute("SELECT liftability FROM bank_liftable_ranked WHERE full_name=? ORDER BY liftability DESC LIMIT 1", (fn,)).fetchone()
        lift = r.get("liftability") or (lr["liftability"] if lr else None) or r.get("reuse_value") or 0
        # fame-trap correction: a repo with high stars but no real adoption is demoted.
        stars = r.get("stars") or 0
        fame_penalty = 0
        if stars > 5000 and (adv is None or adv < 40):
            fame_penalty = 12
        score = lift + (adv if adv is not None else 45) * 0.5 - fame_penalty
        out.append({
            "kind": "repo",
            "full_name": fn,
            "one_liner": r.get("one_line") or r.get("description"),
            "language": r.get("language"),
            "license": r.get("license"),
            "stars": stars,
            "liftability": lift,
            "adoption": adv,
            "adoption_src": adsrc,
            "fame_penalty": fame_penalty,
            "select_score": round(score, 1),
        })
    out.sort(key=lambda x: x["select_score"], reverse=True)
    return out[:limit]


def _json(s):
    try:
        return json.loads(s) if s else []
    except Exception:
        return []


def _top_gotchas(semantics, n=3):
    """Pull the highest-confidence DANGEROUS gotchas -- the real select-value:
    the silent-noop / error-vs-null traps you only learn after shipping."""
    try:
        items = json.loads(semantics) if semantics else []
    except Exception:
        return []
    danger = [g for g in items if g.get("kind") in ("silent-noop", "error-vs-null", "type-surprise")]
    danger.sort(key=lambda g: 0 if g.get("confidence") == "high" else 1)
    picked = (danger or items)[:n]
    return [{"kind": g.get("kind"), "gotcha": g.get("gotcha"), "layer": g.get("evidence_layer")} for g in picked]


def need(cap, limit=5, as_json=False):
    con = connect()
    ensure_log_table(con)
    resolved, bridge, how = resolve_capability(con, cap)
    cards = gather_cards(con, resolved, bridge, limit)
    repos = gather_repos(con, resolved, bridge, limit, exclude={c["full_name"] for c in cards})
    top = cards[0]["full_name"] if cards else (repos[0]["full_name"] if repos else None)
    con.execute("INSERT INTO bank_query_resolution(query,resolved_cap,n_cards,n_repos,top_pick) VALUES(?,?,?,?,?)",
                (cap, resolved, len(cards), len(repos), top))
    con.commit()
    result = {"query": cap, "resolved_capability": resolved, "resolution": how,
              "top_pick": top, "cards": cards, "repos": repos}
    con.close()
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        _print_human(result)
    return result


def _print_human(res):
    print(f"\n  need(\"{res['query']}\")  ->  resolved: {res['resolved_capability']}  [{res['resolution']}]")
    print(f"  TOP PICK: {res['top_pick']}\n")
    print("  === STEERING CARDS (deep-extracted gold; gotchas baked in) ===")
    if not res["cards"]:
        print("    (no deep card for this capability yet -- repos only)")
    for c in res["cards"]:
        print(f"\n  [{c['select_score']:>5}]  {c['full_name']}  ({c['language']}, {c['license']})  lift={c['liftability']} adopt={c['adoption']}")
        print(f"          {c['one_liner']}")
        print(f"          legal: {c['legal_lane'][:90]}")
        if c["requires"]:
            print(f"          requires: {', '.join(c['requires'][:3])}")
        for g in c["gotchas"]:
            print(f"          ! [{g['kind']}/{g['layer']}] {textwrap.shorten(g['gotcha'], 110)}")
        if c["smoke"]:
            print(f"          smoke: {textwrap.shorten(c['smoke'], 100)}")
    print("\n  === BROADER REPO CANDIDATES (ranked liftability+adoption, fame-corrected) ===")
    for r in res["repos"]:
        pen = f" fame-penalty={r['fame_penalty']}" if r["fame_penalty"] else ""
        print(f"  [{r['select_score']:>5}]  {r['full_name']}  ({r['language']})  lift={r['liftability']} adopt={r['adoption']} stars={r['stars']}{pen}")
        if r["one_liner"]:
            print(f"          {textwrap.shorten(str(r['one_liner']), 100)}")
    print()


def list_caps(domain=None):
    con = connect()
    q = "SELECT tag, domain, gold_matches FROM bank_capability_tag"
    args = ()
    if domain:
        q += " WHERE domain=?"; args = (domain,)
    q += " ORDER BY domain, tag"
    for r in con.execute(q, args):
        print(f"  {r['domain']:12} {r['tag']:24} (gold~{r['gold_matches']})")
    con.close()


def show_card(card_id):
    con = connect()
    c = con.execute("SELECT * FROM bank_contractcard WHERE card_id=?", (card_id,)).fetchone()
    if not c:
        print("no such card"); return
    d = dict(c)
    d["provides"] = _json(c["provides"]); d["requires"] = _json(c["requires"])
    d["assumptions"] = _json(c["assumptions"]); d["semantics"] = _json(c["semantics"])
    print(json.dumps(d, indent=2))
    con.close()


def main():
    p = argparse.ArgumentParser(description="Foundry Bank API")
    sub = p.add_subparsers(dest="cmd")
    pn = sub.add_parser("need"); pn.add_argument("capability"); pn.add_argument("--limit", type=int, default=5); pn.add_argument("--json", action="store_true")
    pc = sub.add_parser("caps"); pc.add_argument("--domain")
    pk = sub.add_parser("card"); pk.add_argument("card_id")
    a = p.parse_args()
    if a.cmd == "need":
        need(a.capability, a.limit, a.json)
    elif a.cmd == "caps":
        list_caps(a.domain)
    elif a.cmd == "card":
        show_card(a.card_id)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
