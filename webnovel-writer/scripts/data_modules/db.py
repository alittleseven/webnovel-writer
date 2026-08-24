"""Unified SQLite connection factory.

All data_modules code MUST use this instead of bare sqlite3.connect()
to ensure consistent concurrency settings (WAL + busy_timeout + FK).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]

BUSY_TIMEOUT_MS = 5000


def connect(db_path: PathLike) -> sqlite3.Connection:
    """Open a SQLite connection with WAL, busy_timeout, and foreign_keys ON."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(f"PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
