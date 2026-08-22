#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path

from .test_project_phase import _make_contracts, _make_init_ready
from .test_project_phase import _write_json


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_ensure_scripts_on_path()

import data_modules.doctor as doctor_module  # noqa: E402
from data_modules.projection_log import append_projection_run  # noqa: E402


def test_doctor_init_ready_does_not_require_story_contracts(tmp_path, monkeypatch):
    _make_init_ready(tmp_path)
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    assert report["ok"] is True
    assert report["phase"] == "init_ready"
    assert not [item for item in report["checks"] if str(item["id"]).startswith("file.contract.")]


def test_doctor_missing_init_file_blocks_with_repair(tmp_path, monkeypatch):
    _make_init_ready(tmp_path)
    (tmp_path / "大纲" / "总纲.md").unlink()
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    assert report["ok"] is False
    matches = [item for item in report["checks"] if item["id"] == "file.required.大纲/总纲.md"]
    assert matches
    assert matches[0]["status"] == "error"
    assert matches[0]["repair"]


def test_doctor_checks_contracts_after_story_system_starts(tmp_path, monkeypatch):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    (tmp_path / ".story-system" / "reviews" / "chapter_001.review.json").unlink()
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    assert report["ok"] is False
    contract_checks = [item for item in report["checks"] if item["id"] == "file.contract.review"]
    assert contract_checks
    assert contract_checks[0]["status"] == "error"


def test_doctor_no_project_reports_repair(monkeypatch):
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(None)

    assert report["ok"] is False
    assert report["phase"] == "no_project"
    assert report["recommended_actions"]


def test_doctor_warns_when_old_project_has_commit_without_projection_log(tmp_path, monkeypatch):
    _make_init_ready(tmp_path)
    _write_json(
        tmp_path / ".story-system" / "commits" / "chapter_001.commit.json",
        {
            "meta": {"chapter": 1, "status": "accepted"},
            "projection_status": {"state": "done"},
        },
    )
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    assert report["ok"] is True
    matches = [item for item in report["checks"] if item["id"] == "projection_log.present"]
    assert matches
    assert matches[0]["status"] == "warning"


def test_doctor_blocks_pending_projection_log_run(tmp_path, monkeypatch):
    _make_init_ready(tmp_path)
    commit_payload = {
        "meta": {"chapter": 1, "status": "accepted"},
        "projection_status": {"state": "pending"},
    }
    commit_path = tmp_path / ".story-system" / "commits" / "chapter_001.commit.json"
    _write_json(commit_path, commit_payload)
    append_projection_run(
        tmp_path,
        commit_payload,
        {"state": {"status": "pending"}},
        commit_path=commit_path,
    )
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    matches = [item for item in report["checks"] if item["id"] == "projection_log.latest_run"]
    assert matches
    assert matches[0]["status"] == "error"
    assert report["ok"] is False


def test_sqlite_null_embedding_count_counts_null_rows(tmp_path):
    """P1-9：vectors 表 embedding 为 NULL 的行应被统计（语义检索缺失告警）。"""
    import sqlite3

    db_path = tmp_path / "vectors.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE vectors (chunk_id TEXT PRIMARY KEY, embedding BLOB, content TEXT)"
    )
    conn.execute(
        "INSERT INTO vectors (chunk_id, embedding, content) VALUES ('a', NULL, '仅BM25')"
    )
    conn.execute(
        "INSERT INTO vectors (chunk_id, embedding, content) VALUES ('b', x'0102', '有向量')"
    )
    conn.commit()
    conn.close()

    assert doctor_module._sqlite_null_embedding_count(db_path) == 1


def test_sqlite_null_embedding_count_returns_none_when_table_missing(tmp_path):
    import sqlite3

    db_path = tmp_path / "vectors.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE other (id INTEGER)")
    conn.commit()
    conn.close()

    assert doctor_module._sqlite_null_embedding_count(db_path) is None
