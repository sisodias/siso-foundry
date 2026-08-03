#!/usr/bin/env python3
"""Split the corpus into GitHub release assets and record exact byte offsets.

This is the step that turns "we have 11 GB of books somewhere" into "any agent
can fetch book 84 with one HTTP request".

Two hard constraints shape it:
  * GitHub caps a release asset at 2 GiB. Something must split the corpus.
  * Release assets serve HTTP 206 byte-range requests (verified), so a single
    book can be pulled from a 2 GB asset without downloading the asset.

Given those, the split can be ARBITRARY. Access is random -- an agent wants one
book, or a few dozen, essentially never a whole section -- and a range read costs
the same regardless of which asset it lands in. So we fill assets sequentially by
gid and let the index carry meaning. Choosing a semantic split (by subject, by
century) would optimise for a bulk-sequential workload nobody has exhibited, and
would immediately hit the 356x size imbalance between the largest and smallest
Library of Congress sections.

Each asset is an UNCOMPRESSED tar containing INDIVIDUALLY GZIPPED books.

That split matters and is the whole trick. Compressing the container would
require decompressing everything before the target to reach a byte offset,
destroying random access. Compressing each book separately keeps offsets exact
while still shrinking the corpus ~2.65x (measured on real Gutenberg text), so
the payload is ~6 assets instead of ~16. A range read fetches one compressed
book and gunzips just that -- microseconds, no dependency on anything else in
the asset.

The locator records both `length` (compressed bytes to fetch) and
`raw_length` (what you get after gunzip), so a client knows the exact range to
request and can verify what it got.

Output: asset files plus a locator DB mapping gid -> (asset, offset, length),
which is what ask.py resolves against.

Usage:
  pack_for_release.py --tar txt-files.tar --out ./assets --db locator.sqlite
  pack_for_release.py --tar ... --max-bytes 1900000000   # under the 2GiB cap
"""
import argparse
import gzip
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
import tarfile
import time

# 2 GiB is the hard cap. Default leaves ~200 MB of headroom because tar pads
# members to 512-byte boundaries and a failed upload at 99% is expensive.
DEFAULT_MAX = 1_900_000_000

GID = re.compile(r"(?:^|/)(?:pg)?(\d+)(?:-\d+)?\.txt$", re.IGNORECASE)

SCHEMA = """
CREATE TABLE IF NOT EXISTS location (
  gid        INTEGER NOT NULL,
  asset      TEXT NOT NULL,      -- release asset filename
  member     TEXT NOT NULL,      -- path inside that asset
  offset     INTEGER NOT NULL,   -- byte offset of CONTENT within the asset
  length     INTEGER NOT NULL,   -- COMPRESSED bytes: exactly what to range-request
  raw_length INTEGER,            -- bytes after gunzip, so a client can verify
  encoding   TEXT DEFAULT 'gzip',
  sha256     TEXT,               -- of the RAW text, so drift is detectable
  route      TEXT NOT NULL DEFAULT 'release',
  uri        TEXT,               -- asset download URL once uploaded
  indexed_at TEXT NOT NULL,
  PRIMARY KEY (gid, asset)
);
CREATE INDEX IF NOT EXISTS ix_loc_gid   ON location(gid);
CREATE INDEX IF NOT EXISTS ix_loc_asset ON location(asset);

CREATE TABLE IF NOT EXISTS asset (
  asset      TEXT PRIMARY KEY,
  bytes      INTEGER NOT NULL,
  books      INTEGER NOT NULL,
  sha256     TEXT,
  built_at   TEXT NOT NULL
);
"""


def gid_from(member):
    m = GID.search(member)
    return int(m.group(1)) if m else None


def pack(src_tar, out_dir, db_path, max_bytes, prefix, limit):
    os.makedirs(out_dir, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    idx = 1
    cur = None
    cur_name = None
    cur_books = 0
    rows = []
    assets = []
    seen = skipped = 0
    raw_total = comp_total = 0

    def open_asset(n):
        name = f"{prefix}-{n:03d}.tar"
        return tarfile.open(os.path.join(out_dir, name), "w"), name

    def close_asset():
        nonlocal cur, cur_name, cur_books, rows
        if cur is None:
            return
        cur.close()
        size = os.path.getsize(os.path.join(out_dir, cur_name))
        con.execute(
            "INSERT OR REPLACE INTO asset VALUES (?,?,?,?,?)",
            (cur_name, size, cur_books, None, now),
        )
        con.executemany(
            "INSERT OR REPLACE INTO location VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows
        )
        con.commit()
        assets.append({"asset": cur_name, "bytes": size, "books": cur_books})
        rows = []
        cur_books = 0

    with tarfile.open(src_tar, "r|*") as tf:
        for info in tf:
            if not info.isfile():
                continue
            seen += 1
            gid = gid_from(info.name)
            if gid is None:
                skipped += 1
                continue

            if cur is None:
                cur, cur_name = open_asset(idx)

            data = tf.extractfile(info)
            if data is None:
                continue
            raw = data.read()

            # Compress each book on its own. mtime=0 makes the output
            # deterministic: repacking the same corpus yields byte-identical
            # assets, so a re-run is verifiable rather than merely plausible.
            blob = gzip.compress(raw, compresslevel=9, mtime=0)
            digest = hashlib.sha256(raw).hexdigest()

            member = f"{gid}.txt.gz"
            ti = tarfile.TarInfo(member)
            ti.size = len(blob)
            ti.mtime = 0

            # Offset of the member's CONTENT = current stream position + the
            # 512-byte header tar is about to write.
            offset = cur.fileobj.tell() + tarfile.BLOCKSIZE
            cur.addfile(ti, io.BytesIO(blob))

            rows.append(
                (gid, cur_name, member, offset, len(blob), len(raw),
                 "gzip", digest, "release", None, now)
            )
            cur_books += 1
            raw_total += len(raw)
            comp_total += len(blob)

            if cur.fileobj.tell() >= max_bytes:
                close_asset()
                idx += 1
                cur, cur_name = open_asset(idx)

            if limit and seen >= limit:
                break

    close_asset()
    total = con.execute("SELECT COUNT(*) FROM location").fetchone()[0]
    con.close()

    return {
        "members_scanned": seen,
        "books_packed": total,
        "raw_bytes": raw_total,
        "compressed_bytes": comp_total,
        "compression_ratio": round(raw_total / comp_total, 2) if comp_total else None,
        "skipped_no_gid": skipped,
        "assets": assets,
        "asset_count": len(assets),
        "db": db_path,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tar", required=True)
    ap.add_argument("--out", default="./assets")
    ap.add_argument("--db", default="locator.sqlite")
    ap.add_argument("--max-bytes", type=int, default=DEFAULT_MAX)
    ap.add_argument("--prefix", default="gutenberg")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    t = time.time()
    s = pack(a.tar, a.out, a.db, a.max_bytes, a.prefix, a.limit)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
