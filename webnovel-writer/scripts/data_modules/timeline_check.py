#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""时间线程序化校验（P2-5）。

plan 阶段的时间线校验（单调递增 / 倒计时算术）此前全靠 LLM 自判，
无程序兜底。本模块解析 `大纲/第{volume_id}卷-时间线.md` 的章节时间轴
表格，程序化校验：

1. 所有章节时间锚点已填写（非空、非占位符）；
2. 时间锚点单调递增（无回跳；仅对可解析的天数/年份做算术比较）；
3. 倒计时推进正确（D-N 的 N 单调递减，且单章跳跃不超过 1，除非标注已触发）。

供 `webnovel.py timeline-check` 命令与 write-gate prewrite 调用。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional


# 章节时间轴表格行：| 第N章 | 时间锚点 | 章内跨度 | 与上章间隔 | 倒计时状态 | 备注 |
_CHAPTER_ROW_RE = re.compile(
    r"^\|\s*第\s*(\d+)\s*章\s*\|"
    r"\s*([^|]*?)\s*\|"          # 时间锚点
    r"\s*([^|]*?)\s*\|"          # 章内跨度
    r"\s*([^|]*?)\s*\|"          # 与上章间隔
    r"\s*([^|]*?)\s*\|"          # 倒计时状态
    r"\s*([^|]*?)\s*\|"          # 备注
)
# 倒计时状态：如 "物资耗尽 D-7"、"D-7"、"已触发"
# 带事件名的形式："存粮 D-5"、"风暴 D-10 启动"；裸形式："D-7"
_COUNTDOWN_RE = re.compile(r"(.+?)\s*D[-−](\d+)")
_COUNTDOWN_BARE_RE = re.compile(r"D[-−](\d+)")
# 时间锚点中的天数：如 "末世第1天"、"第3日"
_DAY_RE = re.compile(r"第\s*(\d+)\s*[天日]")
# 时间锚点中的年份：如 "仙历3021年"、"现代2026年"
_YEAR_RE = re.compile(r"(\d{4})\s*年")


def _parse_chapter_axis_rows(content: str) -> List[Dict[str, Any]]:
    """解析章节时间轴表格，返回每章一行数据。"""
    rows: List[Dict[str, Any]] = []
    in_axis_table = False
    for line in content.splitlines():
        stripped = line.strip()
        # 章节时间轴表格以 "## 章节时间轴" 开始，到下一个 "## " 结束
        if stripped.startswith("## 章节时间轴"):
            in_axis_table = True
            continue
        if in_axis_table and stripped.startswith("## "):
            break
        if not in_axis_table:
            continue
        match = _CHAPTER_ROW_RE.match(stripped)
        if not match:
            continue
        chapter = int(match.group(1))
        anchor = match.group(2).strip()
        countdown = match.group(5).strip()
        rows.append({"chapter": chapter, "anchor": anchor, "countdown": countdown})
    return rows


def _extract_day(anchor: str) -> Optional[int]:
    """从时间锚点提取天数（如 "末世第1天" → 1）；无法提取返回 None。"""
    match = _DAY_RE.search(anchor or "")
    return int(match.group(1)) if match else None


def _extract_year(anchor: str) -> Optional[int]:
    """从时间锚点提取年份（如 "仙历3021年" → 3021）。"""
    match = _YEAR_RE.search(anchor or "")
    return int(match.group(1)) if match else None


def _extract_countdown_n(countdown: str) -> Optional[int]:
    """从倒计时状态提取 D-N 的 N；无 D-N 或"已触发"返回 None。

    兼容裸 D-N（如 "D-7"）与带事件名（如 "存粮 D-5"）。
    """
    text = str(countdown or "").strip()
    if not text or text == "-":
        return None
    match = _COUNTDOWN_RE.search(text)
    if match:
        return int(match.group(2))
    match = _COUNTDOWN_BARE_RE.search(text)
    return int(match.group(1)) if match else None


def _extract_countdown_event(countdown: str) -> Optional[tuple[str, int]]:
    """从倒计时状态提取 (事件名, N)。

    事件名用于区分多个并行倒计时事件（如"存粮"与"风暴"），
    避免跨事件误判回退/跳跃。裸 D-N 返回事件名为空字符串。
    """
    text = str(countdown or "").strip()
    if not text or text == "-":
        return None
    match = _COUNTDOWN_RE.search(text)
    if match:
        return match.group(1).strip(), int(match.group(2))
    match = _COUNTDOWN_BARE_RE.search(text)
    return ("", int(match.group(1))) if match else None


def check_timeline(project_root: Path | str, volume_id: int) -> Dict[str, Any]:
    """校验卷时间线表，返回 {ok, checks, errors} 报告。"""
    root = Path(project_root)
    timeline_path = root / "大纲" / f"第{volume_id}卷-时间线.md"
    if not timeline_path.is_file():
        return {
            "ok": False,
            "volume": int(volume_id),
            "timeline_path": str(timeline_path),
            "errors": [{"code": "timeline_file_missing", "message": f"时间线文件不存在: {timeline_path}"}],
            "checks": [],
        }

    content = timeline_path.read_text(encoding="utf-8")
    rows = _parse_chapter_axis_rows(content)
    if not rows:
        return {
            "ok": False,
            "volume": int(volume_id),
            "timeline_path": str(timeline_path),
            "errors": [{"code": "no_chapter_rows", "message": "章节时间轴表格为空或格式无法解析"}],
            "checks": [],
        }

    errors: List[Dict[str, Any]] = []
    checks: List[Dict[str, Any]] = []

    # 1) 时间锚点非空
    empty_anchors = [r["chapter"] for r in rows if not r["anchor"] or r["anchor"].startswith("{")]
    checks.append(
        {
            "id": "timeline.anchor_filled",
            "status": "ok" if not empty_anchors else "error",
            "message": "所有章节时间锚点已填写" if not empty_anchors else f"{len(empty_anchors)} 章时间锚点为空或占位",
            "detail": empty_anchors,
        }
    )
    if empty_anchors:
        errors.append({"code": "anchor_missing", "chapters": empty_anchors})

    # 2) 时间锚点单调递增（天数/年份可解析时做算术比较）
    anchor_monotonic_ok = True
    prev_day: Optional[int] = None
    prev_year: Optional[int] = None
    anchor_issues: List[Dict[str, Any]] = []
    for row in rows:
        day = _extract_day(row["anchor"])
        year = _extract_year(row["anchor"])
        if year is not None and prev_year is not None and year < prev_year:
            anchor_monotonic_ok = False
            anchor_issues.append({"chapter": row["chapter"], "issue": f"年份回跳: {year} < {prev_year}"})
        if day is not None and prev_day is not None and day < prev_day and (year is None or year == prev_year):
            anchor_monotonic_ok = False
            anchor_issues.append({"chapter": row["chapter"], "issue": f"天数回跳: {day} < {prev_day}"})
        if day is not None:
            prev_day = day
        if year is not None:
            prev_year = year
    checks.append(
        {
            "id": "timeline.monotonic",
            "status": "ok" if anchor_monotonic_ok else "error",
            "message": "时间锚点单调递增" if anchor_monotonic_ok else f"{len(anchor_issues)} 处时间回跳",
            "detail": anchor_issues,
        }
    )
    if not anchor_monotonic_ok:
        errors.append({"code": "time_regression", "issues": anchor_issues})

    # 3) 倒计时推进（D-N 单调递减，单章跳跃不超过 1）
    # P2-5 修复：按倒计时事件名分组比较，避免多个并行倒计时事件
    # （如"存粮"与"风暴"）之间误判回退/跳跃。
    countdown_ok = True
    prev_by_event: Dict[str, int] = {}
    countdown_issues: List[Dict[str, Any]] = []
    for row in rows:
        parsed = _extract_countdown_event(row["countdown"])
        if parsed is None:
            continue
        event, n = parsed
        prev_n = prev_by_event.get(event)
        if prev_n is not None:
            if n > prev_n:
                countdown_ok = False
                countdown_issues.append(
                    {"chapter": row["chapter"], "event": event or "(默认)", "issue": f"倒计时回退: D-{n} > D-{prev_n}"}
                )
            elif prev_n - n > 1:
                countdown_ok = False
                countdown_issues.append(
                    {"chapter": row["chapter"], "event": event or "(默认)", "issue": f"倒计时跳跃: D-{prev_n} → D-{n}（跨度过大）"}
                )
        prev_by_event[event] = n
    checks.append(
        {
            "id": "timeline.countdown",
            "status": "ok" if countdown_ok else "error",
            "message": "倒计时推进正确" if countdown_ok else f"{len(countdown_issues)} 处倒计时异常",
            "detail": countdown_issues,
        }
    )
    if not countdown_ok:
        errors.append({"code": "countdown_violation", "issues": countdown_issues})

    return {
        "ok": not errors,
        "volume": int(volume_id),
        "timeline_path": str(timeline_path),
        "chapter_count": len(rows),
        "errors": errors,
        "checks": checks,
    }


def format_timeline_report(report: Dict[str, Any], fmt: str = "text") -> str:
    """渲染校验报告为 text 或 json。"""
    import json

    if fmt == "json":
        return json.dumps(report, ensure_ascii=False, indent=2)

    lines: List[str] = []
    lines.append(f"时间线校验（第{report.get('volume')}卷）: {'通过' if report.get('ok') else '未通过'}")
    for check in report.get("checks") or []:
        mark = "✓" if check["status"] == "ok" else "✗"
        lines.append(f"  {mark} {check['message']}")
        for item in check.get("detail") or []:
            lines.append(f"      - {item}")
    for err in report.get("errors") or []:
        lines.append(f"  ✗ [{err.get('code')}] {err.get('message', '')}")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="校验卷时间线表")
    parser.add_argument("--project-root", required=True, help="书项目根目录")
    parser.add_argument("--volume", type=int, required=True, help="卷号")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    report = check_timeline(args.project_root, args.volume)
    print(format_timeline_report(report, args.format))
    sys.exit(0 if report["ok"] else 1)
