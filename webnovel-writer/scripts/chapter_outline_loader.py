#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

try:
    from chapter_paths import volume_num_for_chapter
except ImportError:  # pragma: no cover
    from scripts.chapter_paths import volume_num_for_chapter


_CHAPTER_RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


def _parse_chapters_range(value: object) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    match = _CHAPTER_RANGE_RE.match(value)
    if not match:
        return None
    try:
        start = int(match.group(1))
        end = int(match.group(2))
    except ValueError:
        return None
    if start <= 0 or end <= 0 or start > end:
        return None
    return start, end


def volume_num_for_chapter_from_state(project_root: Path, chapter_num: int) -> int | None:
    state_path = project_root / ".webnovel" / "state.json"
    if not state_path.exists():
        return None

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(state, dict):
        return None

    progress = state.get("progress")
    if not isinstance(progress, dict):
        return None

    volumes_planned = progress.get("volumes_planned")
    if not isinstance(volumes_planned, list):
        return None

    best: tuple[int, int] | None = None
    for item in volumes_planned:
        if not isinstance(item, dict):
            continue
        volume = item.get("volume")
        if not isinstance(volume, int) or volume <= 0:
            continue
        parsed = _parse_chapters_range(item.get("chapters_range"))
        if not parsed:
            continue
        start, end = parsed
        if start <= chapter_num <= end:
            candidate = (start, volume)
            if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and candidate[1] < best[1]):
                best = candidate

    return best[1] if best else None


def _find_split_outline_file(outline_dir: Path, chapter_num: int) -> Path | None:
    patterns = [
        f"第{chapter_num}章*.md",
        f"第{chapter_num:02d}章*.md",
        f"第{chapter_num:03d}章*.md",
        f"第{chapter_num:04d}章*.md",
    ]
    for pattern in patterns:
        matches = sorted(outline_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def _find_volume_outline_file(project_root: Path, chapter_num: int) -> Path | None:
    outline_dir = project_root / "大纲"
    volume_num = volume_num_for_chapter_from_state(project_root, chapter_num) or volume_num_for_chapter(chapter_num)
    candidates = [
        outline_dir / f"第{volume_num}卷-详细大纲.md",
        outline_dir / f"第{volume_num}卷 - 详细大纲.md",
        outline_dir / f"第{volume_num}卷 详细大纲.md",
    ]
    return next((path for path in candidates if path.exists()), None)


def _extract_outline_section(content: str, chapter_num: int) -> str | None:
    patterns = [
        rf"###\s*第\s*{chapter_num}\s*章[：:]\s*(.+?)(?=###\s*第\s*\d+\s*章|##\s|$)",
        rf"###\s*第{chapter_num}章[：:]\s*(.+?)(?=###\s*第\d+章|##\s|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(0).strip()
    return None


def _parse_chinese_chapter_num(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text in _CHINESE_NUMERAL_DIGITS:
        return _CHINESE_NUMERAL_DIGITS[text]
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = _CHINESE_NUMERAL_DIGITS.get(left, 1 if not left else 0)
        ones = _CHINESE_NUMERAL_DIGITS.get(right, 0) if right else 0
        parsed = tens * 10 + ones
        return parsed or None
    parsed = 0
    for char in text:
        digit = _CHINESE_NUMERAL_DIGITS.get(char)
        if digit is None:
            return None
        parsed = parsed * 10 + digit
    return parsed or None


def _extract_directive_section(content: str, chapter_num: int) -> str | None:
    matches = list(_CHAPTER_HEADING_RE.finditer(content))
    for index, match in enumerate(matches):
        parsed = _parse_chinese_chapter_num(match.group(2))
        if parsed != chapter_num:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        return content[match.start():end].strip()
    return _extract_outline_section(content, chapter_num)


def load_chapter_outline(project_root: Path, chapter_num: int, max_chars: int | None = 1500) -> str:
    outline_dir = project_root / "大纲"

    split_outline = _find_split_outline_file(outline_dir, chapter_num)
    if split_outline is not None:
        text = split_outline.read_text(encoding="utf-8")
        # S4/C4 残留：拆分章纲不再绕过预算——与卷纲路径同用字段边界优先截断
        if max_chars and len(text) > max_chars:
            return _truncate_outline_by_field_priority(text, max_chars)
        return text

    volume_outline = _find_volume_outline_file(project_root, chapter_num)
    if volume_outline is None:
        return f"⚠️ 大纲文件不存在：第 {chapter_num} 章"

    outline = _extract_outline_section(volume_outline.read_text(encoding="utf-8"), chapter_num)
    if outline is None:
        return f"⚠️ 未找到第 {chapter_num} 章的大纲"

    if max_chars and len(outline) > max_chars:
        return _truncate_outline_by_field_priority(outline, max_chars)
    return outline


# P2-2：关键字段标签——截断时优先保留这些行
_PRIORITY_FIELD_LABELS = ("cbn", "cpns", "cen", "必须覆盖节点", "本章禁区")


def _truncate_outline_by_field_priority(outline: str, max_chars: int) -> str:
    """P2-2：按字段边界优先截断——先保留 CBN/CPNs/CEN/禁区等关键字段行，
    再用剩余预算按字符数截断描述文本，避免硬切在关键字段中间。
    """
    lines = outline.splitlines(keepends=True)
    priority_lines: list[str] = []
    other_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if any(
            re.match(rf"^{re.escape(label)}\s*[：:]", stripped, re.IGNORECASE)
            for label in _PRIORITY_FIELD_LABELS
        ):
            priority_lines.append(line)
        else:
            other_lines.append(line)

    # 关键字段行始终保留
    result = "".join(priority_lines)
    # 剩余预算按字符数累积截取其他行
    remaining = max_chars - len(result)
    if remaining > 0:
        accumulated: list[str] = []
        used = 0
        for line in other_lines:
            if used + len(line) > remaining:
                # 截取该行能放下的部分
                fit = remaining - used
                if fit > 0:
                    accumulated.append(line[:fit])
                break
            accumulated.append(line)
            used += len(line)
        result += "".join(accumulated)
    return result.rstrip() + "\n...(已按字段优先级截断)"

_PLOT_SECTION_FIELD_MAP = {
    "cbn": "cbn",
    "cpns": "cpns",
    "cen": "cen",
    "必须覆盖节点": "must_cover_nodes",
    "本章禁区": "forbidden_zones",
}

_CHAPTER_HEADING_RE = re.compile(
    r"^(#{1,6})\s*第\s*([0-9零〇一二两三四五六七八九十]+)\s*章\b.*$",
    re.MULTILINE,
)

_CHINESE_NUMERAL_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

_DIRECTIVE_FIELD_MAP = {
    "目标": "goal",
    "本章目标": "goal",
    "章目标": "goal",
    "阻力": "obstacles",
    "障碍": "obstacles",
    "代价": "cost",
    "时间锚点": "time_anchor",
    "时间": "time_anchor",
    "章内跨度": "chapter_span",
    "章节跨度": "chapter_span",
    "倒计时状态": "countdown",
    "倒计时": "countdown",
    "cbn": "cbn",
    "cpns": "cpns",
    "cen": "cen",
    "必须覆盖节点": "must_cover_nodes",
    "本章禁区": "forbidden_zones",
    "章末未闭合问题": "chapter_end_open_question",
    "章末问题": "chapter_end_open_question",
    "钩子类型": "hook_type",
    "钩子强度": "hook_strength",
    "关键实体": "key_entities",
    "涉及实体": "key_entities",
    "strand": "strand",
    "反派层级": "antagonist_tier",
}

_DIRECTIVE_LIST_FIELDS = {"cpns", "must_cover_nodes", "forbidden_zones", "key_entities"}


def _clean_plot_line(line: str) -> str:
    text = str(line or "").strip()
    # P0-2: strip markdown heading hashes at line start
    text = re.sub(r"^#{1,6}\s*", "", text)
    # P0-2: strip list bullets AND bold markers (**)
    text = re.sub(r"^[\-\*\u2022]+\s*", "", text)
    text = re.sub(r"\*+", "", text)  # strip remaining ** anywhere
    text = re.sub(r"^\d+[\.\u3001]\s*", "", text)
    return text.strip()



def _append_plot_value(target: Dict[str, Any], field: str, value: str) -> None:
    value = _clean_plot_line(value)
    if not value:
        return

    if field in {"cpns", "must_cover_nodes", "forbidden_zones"}:
        target.setdefault(field, [])
        candidates = [value]
        if field in {"must_cover_nodes", "forbidden_zones"}:
            split_values = [part.strip() for part in re.split(r"[、,，；;|]+", value) if part.strip()]
            if split_values:
                candidates = split_values
        for item in candidates:
            if item not in target[field]:
                target[field].append(item)
        return

    if field not in target:
        target[field] = value


def _split_directive_values(value: str) -> list[str]:
    text = _clean_plot_line(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"[、,，；;|]+", text) if part.strip()]


def _append_directive_value(target: Dict[str, Any], field: str, value: str) -> None:
    value = _clean_plot_line(value)
    if not value:
        return
    if field in _DIRECTIVE_LIST_FIELDS:
        target.setdefault(field, [])
        for item in _split_directive_values(value) or [value]:
            if item not in target[field]:
                target[field].append(item)
        return
    if field not in target:
        target[field] = value


def parse_chapter_plot_structure(outline_text: str) -> Dict[str, Any]:
    text = str(outline_text or "")
    if not text or text.startswith("⚠️"):
        return {}

    structure: Dict[str, Any] = {}
    current_field = ""

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            current_field = ""
            continue
        if re.match(r"^#{1,6}\s*第\s*\d+\s*章", stripped):
            current_field = ""
            continue

        cleaned = _clean_plot_line(stripped)
        matched_field = ""
        matched_value = ""
        for label, field in _PLOT_SECTION_FIELD_MAP.items():
            match = re.match(rf"^{re.escape(label)}\s*[：:]\s*(.*)$", cleaned, re.IGNORECASE)
            if match:
                matched_field = field
                matched_value = match.group(1).strip()
                break

        # P0-2: bare heading/label line (no colon value) enters collection mode
        if not matched_field:
            for lbl, fld in _PLOT_SECTION_FIELD_MAP.items():
                if re.match(rf"^{re.escape(lbl)}$", cleaned, re.IGNORECASE):
                    current_field = fld
                    break

        if matched_field:
            current_field = matched_field
            _append_plot_value(structure, matched_field, matched_value)
            continue

        if current_field:
            _append_plot_value(structure, current_field, cleaned)

    cpns = structure.get("cpns") or []
    must_cover_nodes = structure.get("must_cover_nodes") or []
    forbidden_zones = structure.get("forbidden_zones") or []
    if not any([structure.get("cbn"), cpns, structure.get("cen"), must_cover_nodes, forbidden_zones]):
        return {}

    return {
        "cbn": str(structure.get("cbn") or "").strip(),
        "cpns": cpns,
        "cen": str(structure.get("cen") or "").strip(),
        "must_cover_nodes": must_cover_nodes,
        "forbidden_zones": forbidden_zones,
        "source": "chapter_outline",
    }


# S4/C4 残留：plot_structure 注入上下文的限量（字段优先级截断保住标签行，描述文本让预算）
PLOT_STRUCTURE_DEFAULT_MAX_CHARS = 4000


def load_chapter_plot_structure(
    project_root: Path,
    chapter_num: int,
    max_chars: int | None = PLOT_STRUCTURE_DEFAULT_MAX_CHARS,
) -> Dict[str, Any]:
    outline = load_chapter_outline(project_root, chapter_num, max_chars=max_chars)
    return parse_chapter_plot_structure(outline)


def parse_chapter_execution_directive(outline_text: str) -> Dict[str, Any]:
    text = str(outline_text or "")
    if not text or text.startswith("⚠️"):
        return {}

    directive: Dict[str, Any] = {}
    current_field = ""
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            current_field = ""
            continue
        if _CHAPTER_HEADING_RE.match(stripped):
            current_field = ""
            continue

        cleaned = _clean_plot_line(stripped)
        matched_field = ""
        matched_value = ""
        for label, field in _DIRECTIVE_FIELD_MAP.items():
            match = re.match(rf"^{re.escape(label)}\s*[：:]\s*(.*)$", cleaned, re.IGNORECASE)
            if match:
                matched_field = field
                matched_value = match.group(1).strip()
                break

        # P0-2: heading line that is just a field name (no colon) enters collection mode
        if not matched_field:
            for label, field in _PLOT_SECTION_FIELD_MAP.items():
                if re.match(rf"^{re.escape(label)}$", cleaned, re.IGNORECASE):
                    current_field = field
                    break
            else:
                pass
            if current_field and not matched_field:
                # If we just set current_field from a bare heading label,
                # skip appending this heading line itself as a value.
                continue

        if matched_field:
            current_field = matched_field
            _append_directive_value(directive, matched_field, matched_value)
            continue
        if current_field:
            _append_directive_value(directive, current_field, cleaned)

    plot_structure = parse_chapter_plot_structure(text)
    for source_key, target_key in (
        ("cbn", "cbn"),
        ("cpns", "cpns"),
        ("cen", "cen"),
        ("must_cover_nodes", "must_cover_nodes"),
        ("forbidden_zones", "forbidden_zones"),
    ):
        if plot_structure.get(source_key) and not directive.get(target_key):
            directive[target_key] = plot_structure[source_key]

    if directive:
        directive["source"] = "chapter_outline"
    return directive


def load_chapter_execution_directive(project_root: Path, chapter_num: int) -> Dict[str, Any]:
    outline_dir = project_root / "大纲"
    split_outline = _find_split_outline_file(outline_dir, chapter_num)
    if split_outline is not None:
        return parse_chapter_execution_directive(split_outline.read_text(encoding="utf-8"))

    volume_outline = _find_volume_outline_file(project_root, chapter_num)
    if volume_outline is None:
        return {}
    section = _extract_directive_section(volume_outline.read_text(encoding="utf-8"), chapter_num)
    if section is None:
        return {}
    return parse_chapter_execution_directive(section)




