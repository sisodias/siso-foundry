#!/usr/bin/env python3
"""Answer "where does this book actually live?" — the locator index.

The gap this closes: `ask.py --works Plato` returns `{"domain":"book","ref":"1497"}`.
That is an identity, not a location. An agent holding a Frontier Question needs
to go from that reference to actual text, and right now nothing tells it how.

The payload is an 11.2 GB zip containing a single 30.4 GB tar of ~79k text files.
Reading one book by unpacking 30 GB is absurd, so we index the tar ONCE and
record, per book, the exact byte offset and length of its member. After that,
fetching any single book is a seek and a read -- O(1), no unpacking.

That same offset+length is what makes GitHub distribution work: release assets
serve HTTP 206 byte-range requests (verified), so an agent with no local copy
issues one ranged request and gets exactly one book.

The locator therefore stores every route to the same bytes:
    local  -- vault path + byte range
    remote -- release asset URL + byte range
    origin -- the upstream URL it came from, so it can always be re-fetched

Design notes:
  * The index is DERIVED. Losing it costs one re-scan, never data. It is
    deliberately a separate DB from books.sqlite so the catalog stays portable
    and machine-independent while locations are per-machine.
  * A tar member header is 512 bytes; the file content starts immediately after
    and is padded to a 512-byte boundary. Scanning headers alone means we read
    ~40 MB of a 30 GB archive rather than the whole thing.
  * Gutenberg ids are recovered from member paths (e.g. "84/84.txt" or
    "cache/epub/84/pg84.txt"), which is what joins this to books.sqlite.

Usage:
  build_locator.py --tar /path/to/txt-files.tar --db locator.sqlite
  build_locator.py --tar ... --db ... --limit 5000     # partial scan for testing
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import tarfile
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS location (
  gid          INTEGER NOT NULL,     -- joins books.sqlite book.gid
  container    TEXT NOT NULL,        -- which archive holds it
  member       TEXT NOT NULL,        -- path inside the archive
  offset       INTEGER NOT NULL,     -- byte offset of CONTENT (not the header)
  length       INTEGER NOT NULL,
  encoding     TEXT,
  route        TEXT NOT NULL DEFAULT 'local',  -- local | release | origin
  uri          TEXT,                 -- vault path, asset URL, or upstream URL
  indexed_at   TEXT NOT NULL,
  PRIMARY KEY (gid, container, route)
);
CREATE INDEX IF NOT EXISTS ix_loc_gid   ON location(gid);
CREATE INDEX IF NOT EXISTS ix_loc_route ON location(route);

-- One row per archive we have indexed, so a re-scan is detectable and the
-- container can be re-verified without re-reading every member.
CREATE TABLE IF NOT EXISTS container (
  container   TEXT PRIMARY KEY,
  path        TEXT NOT NULL,
  bytes       INTEGER,
  members     INTEGER,
  indexed_at  TEXT NOT NULL
);
"""

# "84/84.txt", "cache/epub/84/pg84.txt", "1/0/0/1001/1001.txt" -- Gutenberg's
# layouts vary by era. The id is the last standalone run of digits before the
# extension, which holds across all of them.
GID = re.compile(r"(?:^|/)(?:pg)?(\d+)(?:-\d+)?\.txt$", re.IGNORECASE)


def gid_from(member):
    m = GID.search(member)
    return int(m.group(1)) if m else None


def build(tar_path, db_path, container_name, uri, limit):
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    rows = []
    seen = skipped = 0

    # Stream the tar reading only headers. tarfile exposes offset_data, which is
    # precisely the byte position of the member's content in the archive.
    with tarfile.open(tar_path, "r|*") as tf:
        for info in tf:
            if not info.isfile():
                continue
            seen += 1
            gid = gid_from(info.name)
            if gid is None:
                skipped += 1
                continue
            rows.append(
                (gid, container_name, info.name, info.offset_data,
                 info.size, None, "local", uri, now)
            )
            if len(rows) >= 5000:
                con.executemany(
                    "INSERT OR REPLACE INTO location VALUES (?,?,?,?,?,?,?,?,?)",
                    rows,
                )
                con.commit()
                rows = []
            if limit and seen >= limit:
                break

    if rows:
        con.executemany(
            "INSERT OR REPLACE INTO location VALUES (?,?,?,?,?,?,?,?,?)", rows
        )

    total = con.execute("SELECT COUNT(*) FROM location").fetchone()[0]
    con.execute(
        "INSERT OR REPLACE INTO container VALUES (?,?,?,?,?)",
        (container_name, tar_path, os.path.getsize(tar_path)
         if os.path.exists(tar_path) else None, total, now),
    )
    con.commit()

    summary = {
        "members_scanned": seen,
        "located": total,
        "skipped_no_gid": skipped,
        "container": container_name,
        "db": db_path,
    }
    con.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tar", required=True)
    ap.add_argument("--db", default="locator.sqlite")
    ap.add_argument("--container", default="gutenberg-txt")
    ap.add_argument("--uri", help="vault path or URL this container is reachable at")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    t = time.time()
    s = build(a.tar, a.db, a.container, a.uri or a.tar, a.limit)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
