#!/usr/bin/env python3
"""
Fix tier/score corruption in SISO_Knowledge page files.

HISTORICAL DIAGNOSIS (not reverified by this source-portability change):
- queries/add_book.py writes `score: 0.0` unconditionally at lines 71 & 87.
- queries/rebuild_index.py uses setdefault at line 90, so the fallback never
  fires once a page carries an explicit score.
- Result: every page stamped at ingest with score=0.0, but tier set by the
  curator. The two cannot agree, because score is a constant and tier is
  evidence-driven.

FIX PROPOSAL: tier DERIVED from score at read/rebuild time, never stored as
an independent field. Score itself should be computed from evidence at
rebuild rather than stamped at ingest. Stale on-disk score/tier are
recomputed.

This script is read-only. --apply is deliberately unavailable. An explicitly
authorised --knowledge-root is required; no owner path is discovered. It proposes
changes where (score, tier) disagree with the historical schema bands:

  A = 8.0–10.0
  B = 5.0–7.9
  C = 0.0–4.9

CONSTRAINT: no Knowledge or Graph writes; this script does not grant access.
"""
import argparse
import sys
from pathlib import Path


# Schema bands from module_templates/page/PAGE_SCHEMA.md
def tier_from_score(score: float) -> str:
    if score >= 8.0:
        return "A"
    if score >= 5.0:
        return "B"
    return "C"


def parse_page(path: Path):
    import yaml  # Optional runtime dependency, not needed for help/input gates.
    try:
        content = path.read_text()
    except Exception:
        return None
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except Exception:
        return None
    return fm, parts[2], content


def derive_score(fm: dict) -> float:
    """
    Compute a score from frontmatter evidence. Until the curator pipeline
    ships a real scorer, fall back to the schema-prescribed default of 7.0
    (the midpoint of the B band — a reasonable "unrated" anchor).

    Evidence signals available right now:
      - len(content)              (longer body => more developed)
      - bool(links_to)            (cross-linked => more connected)
      - bool(contradicts)         (engaged in debate)
      - bool(quality_notes)       (curator touched it)
    """
    body = fm.get("content") or ""
    score = 7.0  # unrated default
    # Tiny nudges from evidence — kept conservative on purpose.
    if isinstance(fm.get("links_to"), list) and fm["links_to"]:
        score += 0.5
    if fm.get("contradicts"):
        score += 0.5
    if fm.get("quality_notes"):
        score += 0.5
    if len(body) > 1500:
        score += 0.5
    return round(min(score, 10.0), 1)


def scan_pages(lib: Path):
    """Yield (path, fm, body, full_text) for every parseable page."""
    for p in (lib / "sections").rglob("p_*.md"):
        if p.name in ("shelf.yaml", "bookcase.yaml", "_index.md", "section.yaml"):
            continue
        parsed = parse_page(p)
        if not parsed:
            continue
        fm, body, full = parsed
        yield p, fm, body, full


def build_diff(lib: Path, limit=None):
    """
    Compute what WOULD change. Returns (changes, totals_before, totals_after).
    """
    changes = []
    counts_before = {"A": 0, "B": 0, "C": 0, "other": 0, "no_tier": 0}
    counts_after = {"A": 0, "B": 0, "C": 0, "other": 0, "no_tier": 0}
    seen = 0

    for p, fm, body, full in scan_pages(lib):
        seen += 1
        old_score = fm.get("score")
        old_tier = fm.get("tier")
        new_score = derive_score(fm)
        new_tier = tier_from_score(new_score)

        # Bucket the BEFORE tier for distribution reporting.
        if old_tier in counts_before:
            counts_before[old_tier] += 1
        elif old_tier is None:
            counts_before["no_tier"] += 1
        else:
            counts_before["other"] += 1

        # After tier is always derived from the new score, so it's always one
        # of A/B/C by construction.
        counts_after[new_tier] += 1

        # Is this a change?
        score_changed = (old_score != new_score)
        tier_changed = (old_tier != new_tier)
        if score_changed or tier_changed:
            changes.append({
                "path": str(p.relative_to(lib)),
                "old_score": old_score,
                "new_score": new_score,
                "old_tier": old_tier,
                "new_tier": new_tier,
                "contradicts_score_band": (old_tier in ("A", "B", "C")
                                           and old_score is not None
                                           and not (
                                               (old_tier == "A" and old_score >= 8.0) or
                                               (old_tier == "B" and 5.0 <= old_score < 8.0) or
                                               (old_tier == "C" and old_score < 5.0)
                                           )),
            })

        if limit and len(changes) >= limit:
            break

    return changes, counts_before, counts_after, seen


def print_diff(changes, limit=10):
    print(f"\n=== SAMPLE OF {min(limit, len(changes))} PROPOSED CHANGES ===\n")
    for c in changes[:limit]:
        flag = "  <-- CONTRADICTS SCHEMA BANDS" if c["contradicts_score_band"] else ""
        print(f"  {c['path']}{flag}")
        print(f"    score: {c['old_score']!r} -> {c['new_score']!r}")
        print(f"    tier:  {c['old_tier']!r} -> {c['new_tier']!r}")
    print()


def print_distribution(before, after):
    print("=== TIER DISTRIBUTION ===")
    print(f"  BEFORE (on-disk): A={before['A']}, B={before['B']}, "
          f"C={before['C']}, other={before['other']}, "
          f"missing={before['no_tier']}")
    print(f"  AFTER  (derived): A={after['A']}, B={after['B']}, "
          f"C={after['C']}")
    total_after = sum(after.values())
    if total_after:
        print(f"  AFTER ratios: A={after['A']/total_after:.1%}, "
              f"B={after['B']/total_after:.1%}, "
              f"C={after['C']/total_after:.1%}")


def main():
    ap = argparse.ArgumentParser(description="Inspect historical tier/score proposals (read-only)")
    ap.add_argument("--apply", action="store_true",
                    help="Unsupported: always refused before reading inputs")
    ap.add_argument("--sample", type=int, default=10,
                    help="Number of sample diffs to print")
    ap.add_argument("--knowledge-root", type=Path, required=True,
                    help="Explicit authorised local corpus root; no path discovery")
    args = ap.parse_args()
    if args.apply:
        ap.error("--apply is unsupported; this reader never writes Knowledge data")
    lib = args.knowledge_root.expanduser().resolve()
    if not (lib / "sections").is_dir():
        ap.error("The selected root has no readable sections directory")

    changes, before, after, seen = build_diff(lib)
    print(f"Scanned {seen} page files")
    print(f"Pages that WOULD change: {len(changes)}")
    print_distribution(before, after)
    print_diff(changes, limit=args.sample)

    print("[DRY RUN] No files modified; applying changes is not implemented.")


if __name__ == "__main__":
    main()
