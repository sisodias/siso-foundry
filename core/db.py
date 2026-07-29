"""Foundry — SQLite connection helpers enforcing the single-writer law.

FOUNDRY-PLAN.html law #1: each domain DB is writable by exactly ONE always-on
collector (on the mini). Everyone else opens read-only. These helpers make the
right thing the easy thing.

  connect_ro(db)  -> read-only connection (file:...?mode=ro). Use everywhere EXCEPT
                     the single always-on writer. Safe under WAL while the writer runs.
  connect_rw(db)  -> writable connection with busy_timeout. ONLY the pinned writer
                     (categorizer / youtube worker / migration scripts) may use this.

Never open a vault SQLite over a network mount for writes (corrupts WAL) — the
writer is always local to the machine that owns the file (the mini).
"""
import sqlite3
from pathlib import Path

BUSY_TIMEOUT_MS = 30000  # wait politely instead of SQLITE_BUSY while another conn writes


def connect_ro(db: str | Path) -> sqlite3.Connection:
    """Read-only connection. The default for all readers (laptop, interface, research, agents)."""
    db = Path(db)
    uri = f"file:{db}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT_MS / 1000)
    con.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    con.row_factory = sqlite3.Row
    return con


def connect_rw(db: str | Path) -> sqlite3.Connection:
    """Writable connection — ONLY for the single pinned writer or migration scripts.
    WAL stays on; busy_timeout set so concurrent readers never error it out."""
    db = Path(db)
    con = sqlite3.connect(str(db), timeout=BUSY_TIMEOUT_MS / 1000)
    con.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    con.row_factory = sqlite3.Row
    return con


if __name__ == "__main__":
    from paths import github_identity_db
    db = github_identity_db()
    con = connect_ro(db)
    n = con.execute("SELECT COUNT(*) FROM repo_category WHERE saucy=1").fetchone()[0]
    print(f"ro connect OK -> saucy={n} in {db}")
    con.close()
