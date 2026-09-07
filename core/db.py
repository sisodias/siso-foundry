"""Foundry SQLite helpers: readers default to read-only; writers need an owner.

These helpers do not discover a machine, grant authority, elect a writer, enable
WAL, verify a backup, or establish runtime health. One authorised local writer
per database remains an operating invariant, not a property enforced here.
"""
import sqlite3
from pathlib import Path

BUSY_TIMEOUT_MS = 30000


def connect_ro(db: str | Path) -> sqlite3.Connection:
    """Open an existing local database read-only, with URI-safe filenames.

    URI encoding is essential for filenames containing question marks, hashes,
    percent signs or spaces. Missing databases must not be silently created.
    """
    uri = Path(db).expanduser().resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT_MS / 1000)
    con.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    con.row_factory = sqlite3.Row
    return con


def connect_rw(db: str | Path) -> sqlite3.Connection:
    """Open writable only under the existing single-writer/migration authority.

    Preserves the previous behavior; does not change journal mode or permissions.
    """
    con = sqlite3.connect(str(Path(db)), timeout=BUSY_TIMEOUT_MS / 1000)
    con.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    con.row_factory = sqlite3.Row
    return con


if __name__ == "__main__":
    from paths import github_identity_db
    db = github_identity_db()
    con = connect_ro(db)
    try:
        n = con.execute("SELECT COUNT(*) FROM repo_category WHERE saucy=1").fetchone()[0]
        print(f"ro connect OK -> saucy={n} in {db}")
    finally:
        con.close()
