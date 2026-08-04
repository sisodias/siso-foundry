#!/usr/bin/env python3
"""Embed passages so search finds ideas rather than words.

The gap this closes: full-text search finds the literal token. Ask for "justice"
and you get passages containing the string -- missing Plato on "what is right",
Aristotle on "the mean", Rawls on "fairness", while returning "Justice of the
Peace" and "Chief Justice", which are job titles. FTS answers "which passages
contain this word"; the questions being asked are "which passages argue this
idea". Those diverge exactly where it matters most -- philosophy, where the same
concept carries a dozen vocabularies across two thousand years.

Measured on the mini (Apple M4, ollama, nomic-embed-text): **55.5 passages/sec,
768 dimensions**. So 500k passages is ~2.5 hours, and the full 41.5M corpus is
about 8 days of continuous compute. That ratio is why this is scoped rather than
run over everything.

SCOPE BY QUESTION, NOT BY CORPUS.
Embedding all 41,501,325 passages would cost days and mostly index romance novels
and juvenile fiction. The tier-1 extraction queue is 17,750 books; the pure
philosophy shelf is 932. Start where the questions are and widen only when a
question needs it -- "read to change an answer", not "index everything in case".

Storage is not the constraint and never was: 500k passages x 768 dims as float16
is ~750 MB, and quantised to int8 it is ~375 MB. A few release assets. The cost
is GENERATING them, which is one-time; querying afterwards is milliseconds.

Vectors are written to the INTERNAL SSD, never the vault. The vault is USB 2.0
and SQLite does many small synchronous writes -- that combination already
produced a disk I/O error at 500 books during the passage build. Move the
finished artifact to the vault when it is cold.

Usage:
  build_embeddings.py --passages passages.sqlite --db vectors.sqlite --gids gids.txt
  build_embeddings.py --passages passages.sqlite --db vectors.sqlite --limit 5000
"""
import argparse
import array
import json
import os
import sqlite3
import sys
import time
import urllib.request

OLLAMA = "http://localhost:11434/api/embeddings"
MODEL = "nomic-embed-text"

SCHEMA = """
CREATE TABLE IF NOT EXISTS vector (
  gid    INTEGER NOT NULL,
  seq    INTEGER NOT NULL,
  dims   INTEGER NOT NULL,
  vec    BLOB NOT NULL,      -- float32 little-endian, dims * 4 bytes
  model  TEXT NOT NULL,
  PRIMARY KEY (gid, seq)
);
CREATE INDEX IF NOT EXISTS ix_vec_gid ON vector(gid);

CREATE TABLE IF NOT EXISTS progress (
  gid        INTEGER PRIMARY KEY,
  passages   INTEGER NOT NULL,
  embedded_at TEXT NOT NULL
);
"""


def embed(text, model, timeout=60):
    req = urllib.request.Request(
        OLLAMA,
        data=json.dumps({"model": model, "prompt": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["embedding"]


def run(passages_db, out_db, gids, limit, model, preview_only):
    src = sqlite3.connect(f"file:{passages_db}?mode=ro", uri=True)
    out = sqlite3.connect(out_db)
    out.executescript(SCHEMA)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Resumable: skip books already done. A run that dies at hour 3 of 8 must
    # continue rather than restart, or the job is effectively un-runnable.
    done = {g for (g,) in out.execute("SELECT gid FROM progress")}

    q = "SELECT gid, seq, preview FROM passage"
    params = []
    if gids:
        marks = ",".join("?" * len(gids))
        q += f" WHERE gid IN ({marks})"
        params = list(gids)
    q += " ORDER BY gid, seq"
    if limit:
        q += f" LIMIT {int(limit)}"

    t0 = time.time()
    n = 0
    skipped = 0
    per_book = {}
    batch = []

    for gid, seq, preview in src.execute(q, params):
        if gid in done:
            skipped += 1
            continue
        text = (preview or "").strip()
        if len(text) < 40:
            continue  # too short to carry meaning; embedding noise helps nobody
        try:
            v = embed(text, model)
        except Exception:
            continue
        blob = array.array("f", v).tobytes()
        batch.append((gid, seq, len(v), blob, model))
        per_book[gid] = per_book.get(gid, 0) + 1
        n += 1

        if len(batch) >= 500:
            out.executemany(
                "INSERT OR REPLACE INTO vector VALUES (?,?,?,?,?)", batch
            )
            out.commit()
            batch = []
            rate = n / max(0.001, time.time() - t0)
            print(f"  {n} embedded  {rate:.1f}/s", file=sys.stderr)

    if batch:
        out.executemany("INSERT OR REPLACE INTO vector VALUES (?,?,?,?,?)", batch)
    out.executemany(
        "INSERT OR REPLACE INTO progress VALUES (?,?,?)",
        [(g, c, now) for g, c in per_book.items()],
    )
    out.commit()

    total = out.execute("SELECT COUNT(*) FROM vector").fetchone()[0]
    elapsed = time.time() - t0
    out.close()
    src.close()
    return {
        "embedded_this_run": n,
        "skipped_already_done": skipped,
        "books_touched": len(per_book),
        "vectors_total": total,
        "rate_per_sec": round(n / max(0.001, elapsed), 1),
        "elapsed_s": round(elapsed, 1),
        "model": model,
        "db": out_db,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--passages", required=True)
    ap.add_argument("--db", default="vectors.sqlite")
    ap.add_argument("--gids", help="file with one gid per line")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--preview-only", action="store_true", default=True)
    a = ap.parse_args()

    gids = None
    if a.gids and os.path.exists(a.gids):
        gids = [int(l.strip()) for l in open(a.gids) if l.strip().isdigit()]

    print(json.dumps(
        run(a.passages, a.db, gids, a.limit, a.model, a.preview_only), indent=2
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
