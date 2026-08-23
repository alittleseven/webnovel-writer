#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2-5：时间线程序化校验测试。"""

import sys
from pathlib import Path


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_ensure_scripts_on_path()

from data_modules.timeline_check import (  # noqa: E402
    _extract_countdown_event,
    _extract_countdown_n,
    _extract_day,
    _extract_year,
    check_timeline,
)


def _write_timeline(tmp_path: Path, body: str, volume: int = 1) -> Path:
    outline_dir = tmp_path / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)
    path = outline_dir / f"第{volume}卷-时间线.md"
    path.write_text(body, encoding="utf-8")
    return path


def _valid_timeline() -> str:
    return (
        "# 第 1 卷 时间线表\n\n"
        "## 卷级时间设定\n\n"
        "| 项目 | 值 |\n|------|-----|\n| 时间基准 | 末世第1天 |\n\n"
        "## 章节时间轴\n\n"
        "| 章节 | 时间锚点 | 章内跨度 | 与上章间隔 | 倒计时状态 | 备注 |\n"
        "|------|---------|---------|-----------|-----------|------|\n"
        "| 第1章 | 末世第1天 清晨 | 4小时 | - | 物资耗尽 D-7 | 开篇 |\n"
        "| 第2章 | 末世第1天 中午 | 3小时 | 0 | D-7 | |\n"
        "| 第3章 | 末世第2天 清晨 | 6小时 | 跨夜 | D-6 | |\n"
        "| 第4章 | 末世第3天 清晨 | 6小时 | 跨日 | D-5 | |\n"
    )


def test_check_timeline_passes_valid(tmp_path):
    _write_timeline(tmp_path, _valid_timeline())

    report = check_timeline(tmp_path, 1)

    assert report["ok"] is True
    assert report["chapter_count"] == 4


def test_check_timeline_missing_file(tmp_path):
    report = check_timeline(tmp_path, 1)

    assert report["ok"] is False
    assert any(e["code"] == "timeline_file_missing" for e in report["errors"])


def test_check_timeline_detects_missing_anchor(tmp_path):
    body = (
        "## 章节时间轴\n\n"
        "| 章节 | 时间锚点 | 章内跨度 | 与上章间隔 | 倒计时状态 | 备注 |\n"
        "|------|---------|---------|-----------|-----------|------|\n"
        "| 第1章 | {末世第1天} | 4小时 | - | D-7 | |\n"
    )
    _write_timeline(tmp_path, body)

    report = check_timeline(tmp_path, 1)

    assert report["ok"] is False
    assert any(e["code"] == "anchor_missing" for e in report["errors"])


def test_check_timeline_detects_time_regression(tmp_path):
    body = (
        "## 章节时间轴\n\n"
        "| 章节 | 时间锚点 | 章内跨度 | 与上章间隔 | 倒计时状态 | 备注 |\n"
        "|------|---------|---------|-----------|-----------|------|\n"
        "| 第1章 | 末世第5天 | 4小时 | - | D-3 | |\n"
        "| 第2章 | 末世第3天 | 3小时 | 回跳 | D-4 | |\n"
    )
    _write_timeline(tmp_path, body)

    report = check_timeline(tmp_path, 1)

    assert report["ok"] is False
    assert any(e["code"] == "time_regression" for e in report["errors"])


def test_check_timeline_detects_countdown_jump(tmp_path):
    body = (
        "## 章节时间轴\n\n"
        "| 章节 | 时间锚点 | 章内跨度 | 与上章间隔 | 倒计时状态 | 备注 |\n"
        "|------|---------|---------|-----------|-----------|------|\n"
        "| 第1章 | 末世第1天 | 4小时 | - | D-7 | |\n"
        "| 第2章 | 末世第1天 | 3小时 | 0 | D-2 | 跳跃 |\n"
    )
    _write_timeline(tmp_path, body)

    report = check_timeline(tmp_path, 1)

    assert report["ok"] is False
    assert any(e["code"] == "countdown_violation" for e in report["errors"])


def test_check_timeline_detects_countdown_regression(tmp_path):
    body = (
        "## 章节时间轴\n\n"
        "| 章节 | 时间锚点 | 章内跨度 | 与上章间隔 | 倒计时状态 | 备注 |\n"
        "|------|---------|---------|-----------|-----------|------|\n"
        "| 第1章 | 末世第1天 | 4小时 | - | D-5 | |\n"
        "| 第2章 | 末世第2天 | 3小时 | 跨日 | D-6 | 回退 |\n"
    )
    _write_timeline(tmp_path, body)

    report = check_timeline(tmp_path, 1)

    assert report["ok"] is False
    assert any(e["code"] == "countdown_violation" for e in report["errors"])


def test_extract_helpers():
    assert _extract_day("末世第1天 清晨") == 1
    assert _extract_day("第3日") == 3
    assert _extract_day("仙历3021年春") is None
    assert _extract_year("仙历3021年春") == 3021
    assert _extract_countdown_n("物资耗尽 D-7") == 7
    assert _extract_countdown_n("D-7") == 7
    assert _extract_countdown_n("已触发") is None
    assert _extract_countdown_n("-") is None


def test_extract_countdown_event_parses_name_and_n():
    assert _extract_countdown_event("存粮 D-5") == ("存粮", 5)
    assert _extract_countdown_event("风暴 D-10 启动") == ("风暴", 10)
    assert _extract_countdown_event("D-7") == ("", 7)
    assert _extract_countdown_event("已触发") is None


def test_check_timeline_multiple_events_no_false_positive(tmp_path):
    """P2-5：多个并行倒计时事件（存粮 + 风暴）不应跨事件误判回退。"""
    body = (
        "## 章节时间轴\n\n"
        "| 章节 | 时间锚点 | 章内跨度 | 与上章间隔 | 倒计时状态 | 备注 |\n"
        "|------|---------|---------|-----------|-----------|------|\n"
        "| 第8章 | 末世第3天 | 5小时 | 跨夜 | 存粮 D-3 | |\n"
        "| 第9章 | 末世第3天 | 6小时 | 0 | 存粮 D-3 | |\n"
        "| 第10章 | 末世第3天 | 3小时 | 0 | 存粮倒计时化解 | |\n"
        "| 第30章 | 末世第14天 | 4小时 | 跨夜 | 风暴 D-10 启动 | |\n"
        "| 第31章 | 末世第14天 | 3小时 | 0 | 风暴 D-10 | |\n"
        "| 第32章 | 末世第15天 | 6小时 | 跨夜 | 风暴 D-9 | |\n"
    )
    _write_timeline(tmp_path, body)

    report = check_timeline(tmp_path, 1)

    assert report["ok"] is True
    assert not any(e["code"] == "countdown_violation" for e in report["errors"])
