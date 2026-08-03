#!/usr/bin/env python3
"""Probe whether a PDF has a usable text layer before committing to extraction.

A scanned PDF looks identical to a born-digital one until you try to read it.
Extracting without this check silently yields a fraction of the book:
the-holographic-universe (342pp) gave 3,707 words because only the front
matter carried text. Sampling pages costs milliseconds and prevents that.

Usage:  probe_text_layer.py FILE.pdf [...]
Exit:   0 all TEXT, 1 any OCR_REQUIRED/PARTIAL, 2 usage/read error.
"""
import json
import subprocess
import sys

SAMPLE_TARGET = 12  # pages sampled across the body
MIN_WORDS_PER_PAGE = 50  # below this a page is effectively blank
MIN_TEXT_RATIO = 0.7  # share of sampled pages needing text to pass


def page_count(path):
    out = subprocess.run(
        ["pdfinfo", path], capture_output=True, text=True, timeout=60
    ).stdout
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1])
    return 0


def words_on_page(path, page):
    """Word count for one page. pdftotext writes to stdout with '-'."""
    r = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), path, "-"],
        capture_output=True, text=True, timeout=120,
    )
    return len(r.stdout.split())


def sample_pages(total):
    """Skip the first 5% — front matter often has text when the body doesn't."""
    start = max(1, int(total * 0.05))
    span = total - start + 1
    if span <= SAMPLE_TARGET:
        return list(range(start, total + 1))
    step = span / SAMPLE_TARGET
    return sorted({int(start + i * step) for i in range(SAMPLE_TARGET)})


def probe(path):
    total = page_count(path)
    if not total:
        return {"file": path, "verdict": "UNREADABLE", "pages": 0}

    pages = sample_pages(total)
    counts = {p: words_on_page(path, p) for p in pages}
    with_text = [p for p, w in counts.items() if w >= MIN_WORDS_PER_PAGE]
    ratio = len(with_text) / len(pages)

    if ratio >= MIN_TEXT_RATIO:
        verdict = "TEXT"
    elif ratio == 0:
        verdict = "OCR_REQUIRED"
    else:
        verdict = "PARTIAL"

    return {
        "file": path,
        "verdict": verdict,
        "pages": total,
        "sampled": len(pages),
        "pages_with_text": len(with_text),
        "text_ratio": round(ratio, 3),
        "median_words_per_sampled_page": sorted(counts.values())[len(counts) // 2],
        "projected_total_words": int(
            sum(counts.values()) / len(counts) * total
        ),
    }


def main():
    paths = sys.argv[1:]
    if not paths:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    results = [probe(p) for p in paths]
    print(json.dumps(results, indent=2))
    return 0 if all(r["verdict"] == "TEXT" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
