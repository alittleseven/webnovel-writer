#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chapter_commit CLI 对损坏 artifact 的友好报错测试。"""
from __future__ import annotations

import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def test_read_json_friendly_error_on_unparseable_artifact(tmp_path, capsys):
    import chapter_commit

    bad = tmp_path / "extraction_result.json"
    bad.write_text('{"accepted_events": [broken', encoding="utf-8")

    try:
        chapter_commit._read_json(str(bad))
    except SystemExit as excinfo:
        assert excinfo.code == 2
        captured = capsys.readouterr()
        assert "无法解析" in captured.err
        assert "extraction_result.json" in captured.err
        assert "Traceback" not in captured.err
    else:
        raise AssertionError("损坏 artifact 应触发 SystemExit(2)")


def test_read_json_friendly_error_on_missing_artifact(tmp_path, capsys):
    import chapter_commit

    missing = tmp_path / "nope.json"

    try:
        chapter_commit._read_json(str(missing))
    except SystemExit as excinfo:
        assert excinfo.code == 2
        captured = capsys.readouterr()
        assert "读取失败" in captured.err
        assert "Traceback" not in captured.err
    else:
        raise AssertionError("缺失 artifact 应触发 SystemExit(2)")
