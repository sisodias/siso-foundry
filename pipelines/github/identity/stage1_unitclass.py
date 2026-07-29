#!/usr/bin/env python3
"""Stage-1 FREE unit_class classifier (no model calls).
Implements PIPE-unit-class-taxonomy.html section 3 over the gold band (reuse 65-88)
AND the fame band (reuse >=89) so we can measure how many famous repos get demoted.
Writes: unit_class, unit_class_source='free', liftability (0-100), compose_note.
Pure metadata. The ambiguous CODE middle is left source='free' but flagged for Stage-2.
"""
import sqlite3, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import github_db

DB = str(github_db())

# --- lexicons (from spec section 3) ---
SUBSTRATE_WORDS = re.compile(r"\b(framework|foundational|canonical|runtime|ecosystem|platform|engine|the de-facto|de facto standard|full-stack framework|web framework|application framework|meta-framework|operating system|kernel|distribution|game engine|standard library)\b", re.I)
COMPONENT_WORDS = re.compile(r"\b(library|parser|middleware|hook|widget|header-only|single-file|single file|drop-in|drop in|utility|helper|wrapper|client|sdk|binding|bindings|formatter|validator|codec|primitive|polyfill|shim|decorator|component|icon set|icons|cli tool|small)\b", re.I)
ENDPRODUCT_WORDS = re.compile(r"\b(self-host|self host|selfhost|dashboard|admin panel|web app|webapp|desktop app|application suite|end-product|all-in-one|complete solution|management system|cms\b|erp\b|crm\b|the app|full application)\b", re.I)
WEIGHTS_WORDS = re.compile(r"\b(model weights|checkpoint|pretrained|pre-trained|dataset|fine-tuned|-7b|-13b|-70b|llm weights|gguf|safetensors)\b", re.I)
CAPABILITY_WORDS = re.compile(r"\b(auth|authentication|billing|payment|job queue|job-queue|workflow|pipeline|crawler|scraper|rag\b|agent|orchestrat|api server|backend service|microservice|feature|flow|integration|connector|gateway|proxy server)\b", re.I)

def legal_lane_from_why(why):
    """Extract legal lane from the [CODE|license] prefix already in `why`."""
    if not why:
        return "unknown"
    head = why[:120].lower()
    if "copyleft" in head or "gpl" in head or "agpl" in head or "lgpl" in head:
        return "copyleft"
    if "noassertion" in head or "no license" in head or "unknown license" in head:
        return "unknown"
    # permissive markers
    if any(t in head for t in ["mit", "apache", "bsd", "isc", "mpl", "unlicense", "0bsd", "zlib", "cc0", "wtfpl", "boost", "postgresql license"]):
        return "permissive"
    return "unknown"

PERMISSIVE_LICENSES = {"MIT","Apache-2.0","BSD-3-Clause","BSD-2-Clause","ISC","Unlicense","MPL-2.0","0BSD","CC0-1.0","MIT-0","Zlib","BSL-1.0","WTFPL","Boost-1.0","PostgreSQL"}

def stage1(stars, descr, why, reuse, language, card_license):
    descr = descr or ""
    why = why or ""
    blob = (descr + " " + why)
    info_tag = "INFO" if why.strip().startswith("[INFO") else ("BOTH" if why.strip().startswith("[BOTH") else "CODE")

    # legal lane: prefer the card license (cleaner) then the why prefix
    if card_license in PERMISSIVE_LICENSES:
        lane = "permissive"
    else:
        lane = legal_lane_from_why(why)

    has_sub = bool(SUBSTRATE_WORDS.search(blob))
    has_comp = bool(COMPONENT_WORDS.search(blob))
    has_end = bool(ENDPRODUCT_WORDS.search(blob))
    has_weights = bool(WEIGHTS_WORDS.search(blob))
    has_cap = bool(CAPABILITY_WORDS.search(blob))
    giant = stars is not None and stars >= 40000
    big = stars is not None and stars >= 10000

    cls = None
    src = "free"
    note = ""
    ambiguous = False

    # ---- decisive free rules ----
    if info_tag == "INFO":
        cls, note = "reference", "INFO branch (curated knowledge)"
    elif has_weights and (language in ("Jupyter Notebook", None) or "model" in blob.lower()):
        cls, note = "reference", "weights/dataset lexicon -> study-only"
    elif giant and has_sub:
        cls, note = "substrate", f"giant({stars//1000}k)+framework-word -> adopt-not-import"
    elif giant and has_end:
        cls, note = "reference", f"giant({stars//1000}k) end-product/monolith -> study-only"
    elif reuse is not None and reuse >= 90 and (has_sub or giant):
        cls, note = "substrate", "reuse>=90 prior + framework/giant"
    elif has_comp and not has_sub and not has_end and (stars is None or stars < 40000):
        cls, note = "component", "component lexicon, narrow surface, not giant"
    elif has_end and not has_comp:
        cls, note = "reference" if (giant) else "capability", "end-product lexicon"
        if cls == "capability":
            note = "end-product but mid-size -> wireable feature (capability)"
    elif has_cap and not has_sub and not has_end:
        cls, note = "capability", "capability/feature lexicon"
    else:
        # ambiguous CODE middle -> needs Stage-2 model pass. Provisional lean.
        ambiguous = True
        if has_sub:
            cls, note = "substrate", "framework-word, sub-giant -> provisional substrate (verify)"
        elif big:
            cls, note = "capability", "mid-large CODE, no clear lexicon -> provisional capability (verify)"
        else:
            cls, note = "component", "small CODE, no lexicon -> provisional component (verify)"

    # ---- liftability score (the REAL re-rated axis) ----
    # base by class: component highest (drop-in), capability high, pattern mid, substrate/reference low
    base = {"component": 85, "capability": 75, "pattern": 45, "substrate": 15, "reference": 8}[cls]
    lift = base
    # legal penalty: non-permissive caps shippability hard
    if lane == "copyleft":
        lift = min(lift, 40)  # design-only at best
        if cls in ("component", "capability"):
            note += "; copyleft -> pattern-ceiling"
    elif lane == "unknown":
        lift = min(lift, 55)
        note += "; license-unknown -> verify before ship"
    # giant penalty: even a 'component' inside a 200k-star monorepo isn't a clean lift
    if giant and cls != "component":
        lift -= 10
    if giant and cls == "substrate":
        lift = min(lift, 12)
    # small-surface bonus: low stars + component words = clean drop-in
    if cls == "component" and (stars or 0) < 20000 and lane == "permissive":
        lift = min(95, lift + 5)
    lift = max(0, min(100, lift))

    return cls, src, lift, note, ambiguous, lane

def main():
    con = sqlite3.connect(DB)
    con.execute("PRAGMA busy_timeout=30000")  # categorizer is live-writing; wait, don't SQLITE_BUSY
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    # E3.0 widen: classify ALL saucy rows still missing a unit_class (idempotent: NULL-only).
    # Original gate was reuse_value>=65; widened to the saucy set so the 9.6k NULL rows get filled.
    rows = cur.execute("""
        SELECT rc.id, rc.full_name, rc.reuse_value, rc.why,
               c.stars, c.description, c.language, c.license
        FROM repo_category rc
        LEFT JOIN repo_card c ON rc.full_name = c.full_name
        WHERE rc.saucy = 1
          AND (rc.unit_class IS NULL OR rc.unit_class = '')
    """).fetchall()
    print(f"rows to classify (saucy, NULL unit_class): {len(rows)}", file=sys.stderr)

    updates = []
    counts = {}
    amb = 0
    for r in rows:
        cls, src, lift, note, ambiguous, lane = stage1(
            r["stars"], r["description"], r["why"], r["reuse_value"], r["language"], r["license"])
        if ambiguous:
            src = "free-prov"  # mark for Stage-2
            amb += 1
        counts[cls] = counts.get(cls, 0) + 1
        updates.append((cls, src, lift, note[:200], r["id"]))

    cur.executemany(
        "UPDATE repo_category SET unit_class=?, unit_class_source=?, liftability=?, compose_note=? WHERE id=?",
        updates)
    con.commit()
    print("CLASS COUNTS:", json.dumps(counts, indent=0), file=sys.stderr)
    print(f"ambiguous (need Stage-2): {amb}", file=sys.stderr)
    con.close()

if __name__ == "__main__":
    main()
