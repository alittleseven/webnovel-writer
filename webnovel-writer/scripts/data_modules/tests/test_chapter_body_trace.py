#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chapter_body_trace hook（S8/P2-6）测试：正文目录 PostToolUse 留痕，不阻断。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
_hooks_dir = str(Path(_scripts_dir).parent / "hooks")
for _p in (_scripts_dir, _hooks_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import chapter_body_trace  # noqa: E402


def _project(tmp_path: Path) -> Path:
    (tmp_path / ".webnovel" / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "正文").mkdir(exist_ok=True)
    return tmp_path


def test_trace_appends_for_body_file(tmp_path):
    project = _project(tmp_path)
    body = project / "正文" / "第0036章-放话.md"

    chapter_body_trace.record_edit(project, "Edit", str(body))

    log = project / ".webnovel" / "logs" / "chapter_body_trace.log"
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["tool"] == "Edit"
    assert record["path"].endswith("第0036章-放话.md")
    assert "time" in record


def test_trace_skips_non_body_file(tmp_path):
    project = _project(tmp_path)

    chapter_body_trace.record_edit(project, "Edit", str(tmp_path / "大纲" / "总纲.md"))

    assert not (project / ".webnovel" / "logs" / "chapter_body_trace.log").exists()


def test_trace_tolerates_missing_file(tmp_path):
    project = _project(tmp_path)

    # 文件尚不存在（新建场景）也应留痕
    chapter_body_trace.record_edit(project, "Write", str(project / "正文" / "第0037章.md"))

    assert (project / ".webnovel" / "logs" / "chapter_body_trace.log").exists()


def test_main_silent_on_bad_stdin(tmp_path, capsys, monkeypatch):
    project = _project(tmp_path)
    monkeypatch.setattr("sys.stdin", type("S", (), {"read": staticmethod(lambda: "not-json")})())
    monkeypatch.setattr(chapter_body_trace, "resolve_project_root", lambda: project)

    assert chapter_body_trace.main() == 0
    assert capsys.readouterr().out == ""


def test_main_silent_without_project(capsys, monkeypatch):
    monkeypatch.setattr(chapter_body_trace, "resolve_project_root", lambda: None)
    monkeypatch.setattr("sys.stdin", type("S", (), {"read": staticmethod(lambda: "{}")})())

    assert chapter_body_trace.main() == 0
    assert capsys.readouterr().out == ""
