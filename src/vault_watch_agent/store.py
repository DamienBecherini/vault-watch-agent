"""The runs kept on the machine (`checkpoints.sqlite` of the guide's working folder), kept light.

LangGraph writes the whole state of a run after each of its steps: a watch leaves 13 to 16 copies of about 400 KB,
and the writes of each step beside them. Only the last copy is ever read: it is what a screen shows, what a run
paused at the review or stopped by an error starts again from. The agent never goes back to an earlier step, so the
copies before the last one are removed, by itself: when a run pauses or ends (the server), when a command that runs
one ends, and when the server starts.

    tidy(home / "checkpoints.sqlite")     # {"checkpoints": 239, "writes": 1100, "freed": 38_000_000}

Measured on the IA on-prem guide (2026-11-20): 26 runs, 45.6 MB before, the last copies 5 MB.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

# What is older than the last checkpoint of its run (and of its namespace). One statement each: SQLite sees the
# table at one instant, so a run writing its next checkpoint meanwhile loses nothing.
_OLDER = ("checkpoint_id < (SELECT MAX(k.checkpoint_id) FROM checkpoints k "
          "WHERE k.thread_id = {t}.thread_id AND k.checkpoint_ns = {t}.checkpoint_ns)")
VACUUM_SHARE, VACUUM_BYTES = 0.2, 1_000_000  # the file is rewritten when a fifth of it, and 1 MB at least, is free


def tidy(db: Path) -> dict:
    """Removes the checkpoints a run no longer needs, and gives the space back to the disk when it is worth it:
    {checkpoints, writes: rows removed, freed: bytes the file lost}. Never raises: a database that is missing, new
    (no table yet) or busy is left as it is, and tidied the next time."""
    done = {"checkpoints": 0, "writes": 0, "freed": 0}
    if not db.is_file():
        return done
    before = weight(db)
    try:
        with closing(sqlite3.connect(db, timeout=10)) as c:
            with c:  # one transaction for both tables
                done["writes"] = c.execute(f"DELETE FROM writes WHERE {_OLDER.format(t='writes')}").rowcount
                done["checkpoints"] = c.execute(f"DELETE FROM checkpoints WHERE {_OLDER.format(t='checkpoints')}").rowcount
            pages, free, size = (c.execute(f"PRAGMA {name}").fetchone()[0] for name in ("page_count", "freelist_count", "page_size"))
            if free * size >= VACUUM_BYTES and free >= pages * VACUUM_SHARE:
                c.execute("VACUUM")  # needs the database to itself for an instant: skipped (below) when it is read
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # the log folded into the file: its weight is the file's
    except sqlite3.Error:
        return done
    done["freed"] = max(0, before - weight(db))
    return done


def weight(db: Path) -> int:
    """Bytes of the database on the disk: its file and its write-ahead log (what was written last is there until
    SQLite folds it into the file)."""
    return sum(p.stat().st_size for p in (db, db.with_name(db.name + "-wal")) if p.is_file())
