#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chapter_meter — 章级 token 计量（D1）。

数据源：ZCode 本地用量库 ``~/.zcode/cli/db/db.sqlite`` 的 ``turn_usage`` 表（只读）。
口径：时间窗内「主会话 + 全部子代理会话」的已完成轮次；缓存读单列；
新增 token = input_tokens - cache_read_input_tokens + output_tokens。

标记文件 ``.webnovel/tmp/chapter_meter.json`` 由 ``meter start`` 写入、``meter stop``
移除；``meter stop`` 同时落 ``chapter_meter_result.json`` 供最终报告引用。
宿主非 ZCode（无用量库）时优雅降级：结果带 ``usage_db_missing``，不阻塞写作流程。
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

MARKER_NAME = "chapter_meter.json"
RESULT_NAME = "chapter_meter_result.json"
_SUBAGENT_LIKE = "sess_subagent%"


def default_db_path() -> Path:
    env = os.environ.get("WEBNOVEL_USAGE_DB", "").strip()
    if env:
        return Path(env)
    return Path.home() / ".zcode" / "cli" / "db" / "db.sqlite"


def marker_path(project_root: Path) -> Path:
    return Path(project_root) / ".webnovel" / "tmp" / MARKER_NAME


def result_path(project_root: Path) -> Path:
    return Path(project_root) / ".webnovel" / "tmp" / RESULT_NAME


def read_marker(project_root: Path) -> Optional[dict[str, Any]]:
    path = marker_path(project_root)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_marker(project_root: Path, marker: dict[str, Any]) -> None:
    path = marker_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")


def _infer_session_anchor(db_path: Path) -> tuple[Optional[str], Optional[int]]:
    """最近完成的非子代理轮次：其 session_id 即当前主会话，完成时刻即计量锚点。"""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT session_id, COALESCE(completed_at, started_at) FROM turn_usage"
            " WHERE status='completed' AND session_id NOT LIKE ?"
            " ORDER BY COALESCE(completed_at, started_at) DESC LIMIT 1",
            (_SUBAGENT_LIKE,),
        ).fetchone()
    finally:
        conn.close()
    return (row[0], int(row[1])) if row else (None, None)


def start_meter(
    project_root: Path,
    chapter: int,
    db_path: Optional[Path] = None,
    session: Optional[str] = None,
) -> dict[str, Any]:
    db_path = Path(db_path) if db_path else default_db_path()
    now_ms = int(time.time() * 1000)
    if session:
        session_id, anchor = str(session), now_ms
    elif db_path.exists():
        session_id, anchor = _infer_session_anchor(db_path)
        session_id, anchor = session_id or "", int(anchor or now_ms)
    else:
        session_id, anchor = "", now_ms
    marker = {
        "chapter": int(chapter),
        "session_id": session_id,
        "started_at": anchor,
        "started_at_iso": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "open",
    }
    _write_marker(Path(project_root), marker)
    return marker


def aggregate_usage(
    project_root: Path,
    marker: dict[str, Any],
    db_path: Optional[Path] = None,
    until_ms: Optional[int] = None,
) -> dict[str, Any]:
    db_path = Path(db_path) if db_path else default_db_path()
    usage: dict[str, Any] = {
        "requests": 0,
        "input": 0,
        "cache_read": 0,
        "output": 0,
        "total": 0,
        "new_tokens": 0,
        "duration_ms": 0,
        "usage_db_missing": not db_path.exists(),
    }
    if usage["usage_db_missing"]:
        return usage

    start = int(marker.get("started_at") or 0)
    sid = str(marker.get("session_id") or "")
    where = ["status='completed'", "started_at >= ?"]
    params: list[Any] = [start]
    if until_ms is not None:
        where.append("COALESCE(completed_at, started_at) <= ?")
        params.append(int(until_ms))
    if sid:
        # 子代理会话 id 与主会话无父子关联，必须按时间窗一并计入
        where.append("(session_id = ? OR session_id LIKE ?)")
        params.extend([sid, _SUBAGENT_LIKE])

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(input_tokens),0), COALESCE(SUM(cache_read_input_tokens),0),"
            " COALESCE(SUM(output_tokens),0), COALESCE(SUM(computed_total_tokens),0),"
            " COALESCE(SUM(duration_ms),0)"
            f" FROM turn_usage WHERE {' AND '.join(where)}",
            params,
        ).fetchone()
    finally:
        conn.close()

    requests, inp, cache, out, total, dur = (int(x or 0) for x in row)
    usage.update(
        requests=requests,
        input=inp,
        cache_read=cache,
        output=out,
        total=total,
        new_tokens=max(0, inp - cache + out),
        duration_ms=dur,
    )
    return usage


def format_usage_line(marker: dict[str, Any], usage: dict[str, Any]) -> str:
    chapter = marker.get("chapter")
    if usage.get("usage_db_missing"):
        return (
            f"SKIP chapter-meter chapter={chapter}"
            " usage_db_missing（未找到 ZCode 用量库，跳过计量；不影响写作流程）"
        )
    return (
        f"OK chapter-meter chapter={chapter}"
        f" requests={usage['requests']}"
        f" input={usage['input']:,}（cache_read={usage['cache_read']:,}）"
        f" output={usage['output']:,}"
        f" total={usage['total']:,}"
        f" new_tokens={usage['new_tokens']:,}"
        f" duration={usage['duration_ms'] / 1000:.1f}s"
    )


def stop_meter(project_root: Path, db_path: Optional[Path] = None) -> str:
    """聚合并关账：写结果文件、移除标记，返回一行结论。"""
    project_root = Path(project_root)
    marker = read_marker(project_root)
    if not marker:
        return "SKIP chapter-meter: no open marker (.webnovel/tmp/chapter_meter.json)"

    usage = aggregate_usage(project_root, marker, db_path=db_path)
    result = {
        "chapter": marker.get("chapter"),
        "session_id": marker.get("session_id"),
        "started_at": marker.get("started_at"),
        "started_at_iso": marker.get("started_at_iso"),
        "stopped_at": int(time.time() * 1000),
        **usage,
    }
    result_file = result_path(project_root)
    result_file.parent.mkdir(parents=True, exist_ok=True)
    result_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    marker_path(project_root).unlink(missing_ok=True)
    return format_usage_line(marker, usage)
