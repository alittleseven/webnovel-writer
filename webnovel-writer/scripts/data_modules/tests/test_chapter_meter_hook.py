#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chapter_meter_hook（D1b UserPromptSubmit 钩子）测试。"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
_hooks_dir = str(Path(_scripts_dir).parent / "hooks")
for _p in (_scripts_dir, _hooks_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import chapter_meter_hook  # noqa: E402

MAIN_SID = "sess_main_abc"
SUB_PREFIX = "sess_subagent_agent_"

SCHEMA = """
CREATE TABLE turn_usage (
    session_id TEXT, turn_id TEXT, trace_id TEXT, user_message_id TEXT,
    status TEXT, started_at INTEGER, first_model_start_at INTEGER,
    first_token_at INTEGER, completed_at INTEGER, duration_ms INTEGER,
    time_to_first_token_ms INTEGER, model_request_count INTEGER,
    model_retry_count INTEGER, tool_call_count INTEGER, tool_error_count INTEGER,
    input_tokens INTEGER, output_tokens INTEGER, reasoning_tokens INTEGER,
    cache_creation_input_tokens INTEGER, cache_read_input_tokens INTEGER,
    computed_total_tokens INTEGER, retryable INTEGER, cancelled_by_user INTEGER,
    context_exceeded INTEGER, error_type TEXT, error_code TEXT
)
"""


def _project_with_marker(tmp_path: Path, *, sid: str = MAIN_SID, rows: list | None = None) -> Path:
    tmp = tmp_path / ".webnovel" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    (tmp / "chapter_meter.json").write_text(
        json.dumps(
            {"chapter": 36, "session_id": sid, "started_at": 1000, "status": "open"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    db_path = tmp_path / "db.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    for r in rows or []:
        conn.execute("INSERT INTO turn_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", r)
    conn.commit()
    conn.close()
    return tmp_path


def _row(sid: str, start_ms: int, total: int) -> tuple:
    return (
        sid, f"t{start_ms}", None, None, "completed", start_ms, start_ms, start_ms,
        start_ms + 1000, 1000, 100, 1, 0, 0, 0,
        total - 50, 50, 0, 0, total - 200, total, 0, 0, 0, None, None,
    )


def test_build_message_none_without_marker(tmp_path):
    (tmp_path / ".webnovel" / "tmp").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")

    assert chapter_meter_hook.build_message(tmp_path) is None


def test_build_message_includes_chapter_totals(tmp_path):
    project = _project_with_marker(
        tmp_path,
        rows=[_row(MAIN_SID, 2000, 300), _row(SUB_PREFIX + "a", 3000, 500)],
    )

    msg = chapter_meter_hook.build_message(project, db_path=project / "db.sqlite")

    assert msg is not None
    assert "第36章" in msg
    assert "总计 800" in msg
    assert "（含子代理）" in msg
    assert "请求 2 次" in msg


def test_build_message_uses_session_hint_when_marker_sid_empty(tmp_path):
    hint = "sess_from_hook"
    project = _project_with_marker(tmp_path, sid="", rows=[_row(hint, 2000, 300)])

    msg = chapter_meter_hook.build_message(project, session_hint=hint, db_path=project / "db.sqlite")

    assert msg is not None
    assert "总计 300" in msg


def test_build_message_none_when_db_missing(tmp_path):
    project = _project_with_marker(tmp_path)

    assert chapter_meter_hook.build_message(project, db_path=tmp_path / "nope.sqlite") is None


def test_build_message_none_when_no_completed_rows(tmp_path):
    project = _project_with_marker(tmp_path, rows=[])

    assert chapter_meter_hook.build_message(project, db_path=project / "db.sqlite") is None


def test_main_prints_additional_context(tmp_path, capsys, monkeypatch):
    project = _project_with_marker(
        tmp_path,
        rows=[_row(MAIN_SID, 2000, 300), _row(SUB_PREFIX + "a", 3000, 500)],
    )
    monkeypatch.setattr(chapter_meter_hook, "resolve_project_root", lambda: project)
    monkeypatch.setattr(
        sys, "argv",
        ["chapter_meter_hook.py", "--session", MAIN_SID],
    )
    monkeypatch.setenv("WEBNOVEL_USAGE_DB", str(project / "db.sqlite"))

    assert chapter_meter_hook.main() == 0
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert "additionalContext" in payload
    assert "第36章" in payload["additionalContext"]


def test_main_silent_without_marker(tmp_path, capsys, monkeypatch):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(chapter_meter_hook, "resolve_project_root", lambda: tmp_path)
    monkeypatch.setenv("WEBNOVEL_USAGE_DB", str(tmp_path / "db.sqlite"))

    assert chapter_meter_hook.main() == 0
    assert capsys.readouterr().out.strip() == ""
