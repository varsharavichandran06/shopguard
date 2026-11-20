"""One helper so every place opens SQLite the same way."""
import shutil
import sqlite3
from pathlib import Path


def open_db(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite has these off by default
    conn.execute("PRAGMA journal_mode = DELETE")  # keep everything in one file, safe to copy
    return conn


def fresh_copy(src: str | Path, dest: str | Path) -> Path:
    """Copy the clean store so each run starts from the same state."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return dest
