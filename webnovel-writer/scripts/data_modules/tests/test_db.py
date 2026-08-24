"""Tests for unified SQLite connection factory."""
import sqlite3

from data_modules.db import connect


def test_connect_sets_wal(tmp_path):
    db = tmp_path / "test.db"
    with connect(db) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_connect_sets_busy_timeout(tmp_path):
    db = tmp_path / "test.db"
    with connect(db) as conn:
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout >= 5000


def test_connect_sets_foreign_keys_on(tmp_path):
    db = tmp_path / "test.db"
    with connect(db) as conn:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1


def test_connect_accepts_str_path(tmp_path):
    db = str(tmp_path / "test.db")
    with connect(db) as conn:
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
        row = conn.execute("SELECT id FROM t").fetchone()
    assert row[0] == 1
