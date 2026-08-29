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
