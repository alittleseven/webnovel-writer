#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chapter_meter 测试：章级 token 计量（D1）。

数据源：ZCode 本地用量库 turn_usage 表（测试用临时 sqlite 造数）。
口径：时间窗内 主会话 + 全部子代理会话；缓存读单列。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from data_modules.chapter_meter import (  # noqa: E402
    aggregate_usage,
    default_db_path,
    read_marker,
    start_meter,
    stop_meter,
)

MAIN_SID = "sess_main_abc"
OTHER_SID = "sess_main_other"
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


def _make_db(tmp_path: Path, rows: list[tuple]) -> Path:
    db_path = tmp_path / "db.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    conn.executemany("INSERT INTO turn_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return db_path


def _row(sid: str, start_ms: int, total: int, *, dur: int = 1000, inp: int = None, out: int = None, cache: int = 0, status: str = "completed"):
    out = out or 0
    inp = inp if inp is not None else total - out
    return (
        sid, f"t{start_ms}", None, None, status, start_ms, start_ms, start_ms,
        start_ms + dur, dur, 100, 1, 0, 0, 0,
        inp, out, 0, 0, cache, total, 0, 0, 0, None, None,
    )


def _project(tmp_path: Path) -> Path:
    (tmp_path / ".webnovel" / "tmp").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    return tmp_path


class TestStartMeter:
    def test_writes_marker_with_inferred_session(self, tmp_path):
        db_path = _make_db(
            tmp_path,
            [_row(MAIN_SID, 1200, 500, dur=0), _row(SUB_PREFIX + "a", 1100, 300), _row(OTHER_SID, 800, 999, dur=0)],
        )
        project = _project(tmp_path)

        marker = start_meter(project, chapter=36, db_path=db_path)

        assert marker["chapter"] == 36
        assert marker["session_id"] == MAIN_SID  # 最近完成的非子代理轮 = 当前会话
        assert marker["started_at"] == 1200  # 推断锚点 = 该轮完成时刻（completed_at）
        assert read_marker(project)["chapter"] == 36

    def test_explicit_session_wins(self, tmp_path):
        db_path = _make_db(tmp_path, [_row(MAIN_SID, 1000, 500)])
        project = _project(tmp_path)

        marker = start_meter(project, chapter=1, db_path=db_path, session="sess_explicit")

        assert marker["session_id"] == "sess_explicit"
        assert marker["started_at"] > 0  # 无可推断轮次时取当前时间


class TestAggregateUsage:
    def test_window_includes_all_main_and_subagent_sessions(self, tmp_path):
        """S13 修复：聚合不再按单主会话过滤——真实场景中写作会话首 turn 未完成时
        推断会指错会话导致漏计主会话（fantasy01 ch36 实测低估 129.6 万）。
        新语义：窗口内全部主会话 + 子代理轮次计入，多主会话在 stop 输出中显式 WARN。"""
        project = _project(tmp_path)
        db_path = _make_db(
            tmp_path,
            [
                _row(MAIN_SID, 1000, 100),  # 窗口前，排除
                _row(MAIN_SID, 2000, 300, inp=250, out=50, cache=200),
                _row(OTHER_SID, 2500, 8888),  # 窗口内另一主会话——计入并 WARN
                _row(SUB_PREFIX + "a", 3000, 500),
                _row(SUB_PREFIX + "b", 4000, 200),
                _row(MAIN_SID, 5000, 999, status="running"),  # 未完成，排除
            ],
        )
        marker = {"session_id": MAIN_SID, "chapter": 36, "started_at": 1500}

        usage = aggregate_usage(project, marker, db_path=db_path)

        assert usage["requests"] == 4
        assert usage["total"] == 300 + 8888 + 500 + 200
        assert usage["cache_read"] == 200
        assert sorted(usage["main_sessions"]) == sorted([MAIN_SID, OTHER_SID])

    def test_stop_warns_on_parallel_main_sessions(self, tmp_path, capsys):
        project = _project(tmp_path)
        db_path = _make_db(
            tmp_path,
            [
                _row(MAIN_SID, 2000, 300, dur=0),
                _row(OTHER_SID, 2500, 700, dur=0),
            ],
        )
        # 手写 marker：窗口覆盖两个主会话（绕过「最近完成轮」推断锚点）
        marker_file = project / ".webnovel" / "tmp" / "chapter_meter.json"
        marker_file.parent.mkdir(parents=True, exist_ok=True)
        marker_file.write_text(
            json.dumps({"chapter": 36, "session_id": MAIN_SID, "started_at": 1500, "status": "open"}),
            encoding="utf-8",
        )

        line = stop_meter(project, db_path=db_path)

        assert "parallel_main_sessions=2" in line
        assert "total=1,000" in line

    def test_stop_closes_marker_and_writes_result(self, tmp_path, capsys):
        project = _project(tmp_path)
        # 主会话 + 子代理都在推断锚点（2000）之后：一并计入
        db_path = _make_db(
            tmp_path,
            [_row(MAIN_SID, 2000, 300, dur=0, inp=250, out=50, cache=200), _row(SUB_PREFIX + "a", 2500, 500)],
        )
        start_meter(project, chapter=36, db_path=db_path)  # 推断：session=MAIN_SID, anchor=2000

        line = stop_meter(project, db_path=db_path)

        assert line.startswith("OK chapter-meter")
        assert "chapter=36" in line
        assert "requests=2" in line
        assert "total=800" in line
        assert "new_tokens=600" in line  # (250-200+50) + (500-0+0)
        assert "\n" not in line
        result = json.loads((project / ".webnovel" / "tmp" / "chapter_meter_result.json").read_text(encoding="utf-8"))
        assert result["total"] == 800
        assert read_marker(project) is None  # 关账后标记移除

    def test_missing_db_degrades_gracefully(self, tmp_path):
        project = _project(tmp_path)
        start_meter(project, chapter=1, db_path=tmp_path / "nope.sqlite", session=MAIN_SID)

        line = stop_meter(project, db_path=tmp_path / "nope.sqlite")

        assert "usage_db_missing" in line


class TestDefaultDbPath:
    def test_env_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("WEBNOVEL_USAGE_DB", str(tmp_path / "x.sqlite"))
        assert default_db_path() == tmp_path / "x.sqlite"

    def test_default_points_at_zcode_db(self, monkeypatch):
        monkeypatch.delenv("WEBNOVEL_USAGE_DB", raising=False)
        assert default_db_path().name == "db.sqlite"
