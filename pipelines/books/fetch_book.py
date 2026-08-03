#!/usr/bin/env python3
"""Fetch one book, or one passage, from anywhere — no local corpus required.

This is the client end of the chain. The index says a book exists; the locator
says where its bytes are; this issues the single HTTP Range request that gets
them. Verified against the live release: 26,460 bytes fetched out of a 1.77 GB
asset in 0.37s, yielding the full 101,354-character text.

Two granularities, and the second is the one that matters:

  --gid 84              the whole book
  --gid 84 --passage 12 one paragraph

The passage layer indexes 41,501,325 paragraphs across 77,540 books as byte
ranges into the source text. A question about justice does not want 448 KB of
The Republic; it wants one of those paragraphs. Fetching a passage still costs
one request, because the passage offset is applied AFTER decompressing the
book -- gzip is per-book, so the book is the smallest network unit, but the
passage is the smallest unit an agent has to read.

Routes are tried cheapest-first and every one is a fallback for the next:
  1. local vault file, if this machine has the corpus (no network at all)
  2. GitHub release asset by byte range (~0.3s, works anywhere, no auth)
  3. Project Gutenberg directly (always works, slowest, and the only route that
     survives us deleting everything)

Integrity is checked when the locator carries a SHA-256, which turns silent
corruption into a loud failure. That is also what makes this a pinned edition:
if upstream re-transcribes a book, the hash stops matching instead of the change
arriving unnoticed.

Usage:
  fetch_book.py --gid 84 --locator locator.sqlite
  fetch_book.py --gid 84 --passage 12 --locator locator.sqlite --passages passages.sqlite
  fetch_book.py --gid 84 --route origin        # skip the index entirely
"""
import argparse
import gzip
import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.request

RELEASE = ("https://github.com/sisodias/siso-book-library/releases/download/"
           "payload-v1/{asset}")
ORIGIN = "https://www.gutenberg.org/ebooks/{gid}.txt.utf-8"


def from_local(vault_dir, asset, offset, length):
    path = os.path.join(vault_dir, asset)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        f.seek(offset)
        return f.read(length)


def from_release(asset, offset, length):
    """One HTTP Range request. GitHub release assets return 206 -- verified."""
    req = urllib.request.Request(
        RELEASE.format(asset=asset),
        headers={"Range": f"bytes={offset}-{offset + length - 1}",
                 "User-Agent": "siso-book-library/1.0"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def from_origin(gid):
    req = urllib.request.Request(
        ORIGIN.format(gid=gid), headers={"User-Agent": "siso-book-library/1.0"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def fetch(gid, locator_db, vault_dir, route_pref):
    """Return (text, route_used, elapsed)."""
    t0 = time.time()

    if route_pref == "origin" or not locator_db or not os.path.exists(locator_db):
        return from_origin(gid).decode("utf-8", "replace"), "origin", time.time() - t0

    con = sqlite3.connect(f"file:{locator_db}?mode=ro", uri=True)
    row = con.execute(
        "SELECT asset, offset, length, raw_length, sha256 FROM location "
        "WHERE gid = ? LIMIT 1",
        (gid,),
    ).fetchone()
    con.close()

    if not row:
        # Unknown to the locator is not an error: origin always works, which is
        # why it is a route and not a fallback hack.
        return from_origin(gid).decode("utf-8", "replace"), "origin", time.time() - t0

    asset, offset, length, raw_length, sha = row

    blob = None
    used = None
    if vault_dir and route_pref in (None, "local"):
        blob = from_local(vault_dir, asset, offset, length)
        used = "local" if blob else None
    if blob is None:
        blob = from_release(asset, offset, length)
        used = "release"

    raw = gzip.decompress(blob)

    if sha:
        got = hashlib.sha256(raw).hexdigest()
        if got != sha:
            raise SystemExit(
                f"INTEGRITY FAILURE gid={gid}: expected {sha[:16]}… got {got[:16]}…\n"
                "The bytes do not match what was indexed. Do not trust this text."
            )
    if raw_length and len(raw) != raw_length:
        raise SystemExit(
            f"LENGTH MISMATCH gid={gid}: expected {raw_length} got {len(raw)}"
        )

    return raw.decode("utf-8", "replace"), used, time.time() - t0


def passage_of(text, gid, seq, passages_db):
    """Slice one paragraph out of the fetched book by its indexed byte range."""
    con = sqlite3.connect(f"file:{passages_db}?mode=ro", uri=True)
    row = con.execute(
        "SELECT start, end, heading FROM passage WHERE gid=? AND seq=?",
        (gid, seq),
    ).fetchone()
    con.close()
    if not row:
        return None, None
    start, end, heading = row
    return text[start:end], heading


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gid", type=int, required=True)
    ap.add_argument("--passage", type=int, help="passage seq within the book")
    ap.add_argument("--locator", default="locator.sqlite")
    ap.add_argument("--passages", default="passages.sqlite")
    ap.add_argument("--vault", help="dir holding the asset tars, if local")
    ap.add_argument("--route", choices=["local", "release", "origin"])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--chars", type=int, default=600, help="preview length")
    a = ap.parse_args()

    text, route, elapsed = fetch(a.gid, a.locator, a.vault, a.route)

    out = {"gid": a.gid, "route": route, "elapsed_s": round(elapsed, 3),
           "chars": len(text)}

    if a.passage is not None and os.path.exists(a.passages):
        chunk, heading = passage_of(text, a.gid, a.passage, a.passages)
        if chunk is None:
            out["error"] = f"no passage {a.passage} for gid {a.gid}"
        else:
            out.update({"passage": a.passage, "heading": heading,
                        "text": chunk.strip()})
    else:
        out["preview"] = " ".join(text[:a.chars].split())

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
