#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review_pipeline.py 输出紧凑化测试。"""
from __future__ import annotations

import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def test_summarize_review_payload_is_compact_one_liner():
    import review_pipeline

    payload = {
        "chapter": 1,
        "review_result": {"blocking_count": 0, "issues_count": 0, "issues": []},
        "metrics": {"overall_score": 8.5, "report_file": "审查报告/第1章审查报告.md"},
        "anti_patterns_added": 0,
    }

    line = review_pipeline.summarize_review_payload(payload)

    assert line.startswith("DONE")
    assert "\n" not in line
    assert len(line) < 500
    assert "chapter=1" in line
    assert "blocking=0" in line and "issues=0" in line
    assert "review_result" not in line
    assert "report=" in line


def test_summarize_review_payload_blocking_without_report():
    import review_pipeline

    payload = {
        "chapter": 3,
        "review_result": {"blocking_count": 2, "issues_count": 5},
        "metrics": {},
        "anti_patterns_added": 1,
    }

    line = review_pipeline.summarize_review_payload(payload)

    assert line.startswith("DONE")
    assert "blocking=2" in line and "issues=5" in line
    assert "anti_patterns=1" in line
    assert "report=" not in line


def test_main_friendly_error_on_unparseable_review_json(tmp_path, capsys, monkeypatch):
    import sys

    import pytest

    import review_pipeline

    bad = tmp_path / "review_results.json"
    bad.write_text('{"chapter": 1, "issues": [broken', encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "review_pipeline",
            "--project-root",
            str(tmp_path),
            "--chapter",
            "1",
            "--review-results",
            str(bad),
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        review_pipeline.main()

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "无法解析" in captured.err
    assert "review_results.json" in captured.err
    assert "Traceback" not in captured.err


def test_main_friendly_error_on_missing_review_json(tmp_path, capsys, monkeypatch):
    import sys

    import pytest

    import review_pipeline

    missing = tmp_path / "nope.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "review_pipeline",
            "--project-root",
            str(tmp_path),
            "--chapter",
            "1",
            "--review-results",
            str(missing),
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        review_pipeline.main()

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "读取失败" in captured.err
    assert "Traceback" not in captured.err
