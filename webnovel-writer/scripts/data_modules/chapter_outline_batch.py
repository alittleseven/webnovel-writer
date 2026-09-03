"""章纲批量生成（webnovel-copilot-300 · M1/T8，流程 F-04）。

章纲卡 = 平铺 front matter（无依赖解析，列表字段存 JSON 数组）+ 正文。
- 一批 ≤8 张（P7：一次确认一批，非逐张）；写入 状态: draft。
- 批内自检（warning，不阻断创建）：节点非空 / 字数范围 / 承诺前缀 / 时间锚重复。
- confirm 翻转 draft→confirmed 并留 journal（adopt）。
字段约定见 06 §2。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .author_journal import append_events

BATCH_SCHEMA_VERSION = "chapter-card/1"
MAX_BATCH = 8
REQUIRED_FIELDS: tuple[str, ...] = ("章节号", "标题", "卷", "时间锚", "节点", "字数目标")
LIST_FIELDS: tuple[str, ...] = ("节点", "禁区", "承诺推进", "战力事件", "素材引用")
_FIELD_ORDER: tuple[str, ...] = (
    "章节号", "标题", "卷", "状态", "时间锚", "节点", "禁区", "承诺推进", "战力事件", "素材引用", "字数目标",
)
WORD_MIN, WORD_MAX = 500, 10000
_PROMISE_PREFIXES = ("F-", "S-", "R-")


def _chapter_dir(project_root: str | Path) -> Path:
    return Path(project_root) / "大纲" / "章纲"


def _serialize_front_matter(card: dict[str, Any]) -> str:
    lines = ["---"]
    for key in _FIELD_ORDER:
        if key not in card:
            continue
        value = card[key]
        if key in LIST_FIELDS:
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def parse_chapter_card(text: str) -> tuple[dict[str, Any], str]:
    """解析章纲卡：返回 (字段 dict，正文)。列表字段还原为 list。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fields: dict[str, Any] = {}
    for line in parts[1].splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key in LIST_FIELDS:
            try:
                fields[key] = json.loads(value)
            except json.JSONDecodeError:
                fields[key] = [value] if value else []
        else:
            fields[key] = value
    return fields, parts[2].lstrip("\n")


def self_check_batch(cards: list[dict[str, Any]]) -> list[str]:
    """批内自检，返回问题描述列表（warning 级，不阻断）。"""
    problems: list[str] = []
    seen_anchors: dict[str, int] = {}
    for card in cards:
        chapter = card.get("章节号")
        label = f"章{chapter}"
        nodes = card.get("节点") or []
        if not nodes:
            problems.append(f"{label} 节点为空（至少需 1 个 CBN）")
        try:
            words = int(card.get("字数目标", 0))
        except (TypeError, ValueError):
            words = 0
            problems.append(f"{label} 字数目标非整数")
        if words and not (WORD_MIN <= words <= WORD_MAX):
            problems.append(f"{label} 字数目标 {words} 超出建议范围 {WORD_MIN}-{WORD_MAX}")
        for promise in card.get("承诺推进") or []:
            if not str(promise).startswith(_PROMISE_PREFIXES):
                problems.append(f"{label} 承诺推进 '{promise}' 缺少 F-/S-/R- 前缀")
        anchor = str(card.get("时间锚") or "")
        if anchor:
            if anchor in seen_anchors:
                problems.append(f"{label} 时间锚 '{anchor}' 与章{seen_anchors[anchor]} 重复")
            else:
                seen_anchors[anchor] = chapter
    return problems


def create_chapter_batch(project_root: str | Path, cards: list[dict[str, Any]]) -> dict[str, Any]:
    """创建一批章纲卡（状态 draft）。返回 {ok, written, checks, error?}。"""
    if len(cards) > MAX_BATCH:
        return {"ok": False, "error": "batch_too_large", "max": MAX_BATCH, "count": len(cards)}
    chapter_numbers: list[int] = []
    for card in cards:
        for field in REQUIRED_FIELDS:
            if field not in card or card[field] in (None, "", []):
                return {"ok": False, "error": "missing_field", "field": field, "chapter": card.get("章节号")}
        try:
            chapter = int(card["章节号"])
        except (TypeError, ValueError):
            return {"ok": False, "error": "invalid_chapter", "chapter": card.get("章节号")}
        if chapter in chapter_numbers:
            return {"ok": False, "error": "duplicate_chapter", "chapter": chapter}
        chapter_numbers.append(chapter)

    problems = self_check_batch(cards)
    chapter_dir = _chapter_dir(project_root)
    chapter_dir.mkdir(parents=True, exist_ok=True)
    written: list[int] = []
    for card in cards:
        chapter = int(card["章节号"])
        payload = dict(card)
        payload["状态"] = "draft"
        text = _serialize_front_matter(payload) + "\n" + str(card.get("正文", "")).strip() + "\n"
        (chapter_dir / f"{chapter:04d}.md").write_text(text, encoding="utf-8", newline="\n")
        written.append(chapter)

    append_events(
        project_root,
        [
            {
                "actor": "ai",
                "action": "regen",
                "domain": "章纲",
                "path": f"大纲/章纲/batch({len(written)})",
                "change_kind": "add",
                "diff_stat": {"ins": len(written)},
                "summary": f"批量生成 {len(written)} 张章纲卡",
                "impact": [],
            }
        ],
    )
    return {
        "ok": True,
        "schema_version": BATCH_SCHEMA_VERSION,
        "written": sorted(written),
        "checks": problems,
    }


def confirm_chapter_batch(project_root: str | Path, chapters: list[int]) -> dict[str, Any]:
    """一批确认：draft→confirmed，逐章留 journal。"""
    chapter_dir = _chapter_dir(project_root)
    confirmed: list[int] = []
    for chapter in chapters:
        path = chapter_dir / f"{int(chapter):04d}.md"
        if not path.is_file():
            return {"ok": False, "error": "chapter_missing", "chapter": chapter}
        text = path.read_text(encoding="utf-8")
        text = text.replace("状态: draft", "状态: confirmed", 1)
        path.write_text(text, encoding="utf-8", newline="\n")
        confirmed.append(int(chapter))
        append_events(
            project_root,
            [
                {
                    "actor": "author",
                    "action": "adopt",
                    "domain": "章纲",
                    "path": f"大纲/章纲/{int(chapter):04d}.md",
                    "change_kind": "structure",
                    "diff_stat": {"ins": 0, "del": 0},
                    "summary": f"确认章纲 {int(chapter)}",
                    "impact": [],
                }
            ],
        )
    return {"ok": True, "confirmed": confirmed}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="章纲批量（T8）")
    parser.add_argument("action", choices=["confirm"])
    parser.add_argument("--chapters", default="", help="逗号分隔章号")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    chapters = [int(c) for c in args.chapters.split(",") if c.strip()]
    if args.action == "confirm":
        report = confirm_chapter_batch(root, chapters)
    else:
        report = {"ok": False, "error": "unknown"}
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("OK" if report.get("ok") else f"ERROR {report.get('error')}")
    return 0 if report.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
