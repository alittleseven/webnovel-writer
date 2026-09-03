"""impact 引用反查（webnovel-copilot-300 · M0/T5，流程 F-07 第 1-2 步）。

对指定文件路径输出受影响面：
- 章纲 NNNN.md → chapter:NNNN（context-stale）
- 定版素材 素材/定版/... → 使用轨迹.jsonl 反查引用章
- 战力锚点 设定/力量锚点.yaml → 战例账本章号
- 正文 定稿/正文/NNNN-*.md → chapter:NNNN（fact-recheck + 摘要重建建议）
- 其余域 → 最小报告

三选项裁决建议（定版/战力/正文类变更，F-07）：只改今后 / 全书 retcon / 还原。
红线：只读分析；yaml 解析失败降级为空结果不炸。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .author_sync import classify_path

IMPACT_SCHEMA_VERSION = "impact/1"

USAGE_TRAIL_REL = Path("素材") / "使用轨迹.jsonl"
POWER_ANCHOR_REL = Path("设定") / "力量锚点.yaml"

_CHAPTER_NUM_RE = re.compile(r"(\d{1,4})")

# 活层素材表名 ↔ 条目 id 前缀（csv/README 规范；反查按 表级=版本+前缀 匹配）
TABLE_PREFIXES: dict[str, str] = {
    "桥段": "TR",
    "场景写法": "SP",
    "写作技法": "WT",
    "爽点节奏": "PA",
    "人设关系": "CH",
    "金手指零件": "SY",
    "金手指与设定": "SY",
    "命名风格": "NR",
    "世界观零件": "GR",
    "台词金句": "RS",
    "梗与反差": "MX",
}

_THREE_OPTIONS = [
    "① 只改今后：定版/锚点不动，新章按新规则执行并记录例外",
    "② 全书 retcon：按影响清单逐章修改，演化/记录 retcon(N) 事务",
    "③ 还原：放弃本次修改，保持既有定版",
]


def _chapter_key(stem: str) -> str | None:
    match = _CHAPTER_NUM_RE.search(stem)
    return match.group(1) if match else None


def _usage_trail_chapters(root: Path, definitive_path: str) -> list[int]:
    """从使用轨迹反查引用章（表级匹配 = 定版版本 + 条目id 表前缀）。"""
    trail = root / USAGE_TRAIL_REL
    if not trail.is_file():
        return []
    version_match = re.search(r"定版[/\\](v\d+)", definitive_path)
    version = version_match.group(1) if version_match else None
    table_match = re.search(r"定版[/\\]v\d+[/\\](.+?)\.csv$", definitive_path)
    prefix = TABLE_PREFIXES.get(table_match.group(1)) if table_match else None
    chapters: list[int] = []
    with trail.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            entry_version = str(entry.get("定版版本") or "")
            if version and entry_version and entry_version != version:
                continue
            entry_id = str(entry.get("条目id") or "")
            if prefix and not entry_id.startswith(prefix + "-"):
                continue
            chapter = entry.get("章")
            if isinstance(chapter, int) and chapter not in chapters:
                chapters.append(chapter)
    return sorted(chapters)


def _power_ledger_chapters(root: Path) -> list[int]:
    """战例账本章号（yaml 宽松解析：只取『章: N』行，坏 yaml 不炸）。"""
    anchor = root / POWER_ANCHOR_REL
    if not anchor.is_file():
        return []
    chapters: list[int] = []
    for line in anchor.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.search(r"章:\s*(\d{1,4})", line)
        if match:
            chapter = int(match.group(1))
            if chapter not in chapters:
                chapters.append(chapter)
    return sorted(chapters)


def analyze_impact(project_root: str | Path, path: str) -> dict[str, Any]:
    """对给定路径输出影响报告（只读）。"""
    root = Path(project_root)
    normalized = path.replace("\\", "/")
    domain = classify_path(normalized)
    stem = Path(normalized).stem

    report: dict[str, Any] = {
        "schema_version": IMPACT_SCHEMA_VERSION,
        "ok": True,
        "path": normalized,
        "domain": domain,
        "chapter": None,
        "affected_chapters": [],
        "stale_targets": [],
        "impacts": [],
        "suggestions": [],
        "options": [],
    }

    if domain == "章纲":
        chapter = _chapter_key(stem)
        report["chapter"] = chapter
        if chapter:
            report["stale_targets"].append(f"chapter:{chapter}")
            report["impacts"].append(f"context-stale:{chapter}")
        report["suggestions"].append("重新编译本章合同（story-system）后再起草")

    elif domain == "素材" and "/定版/" in normalized:
        report["affected_chapters"] = _usage_trail_chapters(root, normalized)
        report["stale_targets"].append(f"material:{normalized}")
        report["impacts"].append("引用章反查")
        if report["affected_chapters"]:
            report["impacts"].append("受影响章：" + "、".join(str(c) for c in report["affected_chapters"]))
            report["suggestions"].append("受影响章按三选项裁决处理")
        report["options"] = list(_THREE_OPTIONS)

    elif domain == "战力":
        report["affected_chapters"] = _power_ledger_chapters(root)
        report["stale_targets"].append("power-anchor")
        report["impacts"].append("战例对账")
        if report["affected_chapters"]:
            report["impacts"].append("战例章：" + "、".join(str(c) for c in report["affected_chapters"]))
        report["options"] = list(_THREE_OPTIONS)

    elif domain == "正文":
        chapter = _chapter_key(stem)
        report["chapter"] = chapter
        if chapter:
            report["stale_targets"].append(f"chapter:{chapter}")
            report["impacts"].append(f"fact-recheck:{chapter}")
        report["suggestions"].append("重跑该章事实一致性审查（reviewer）")
        report["suggestions"].append("章摘要/记忆投影需重算（projections）")
        report["options"] = list(_THREE_OPTIONS)

    return report


def format_impact_report(report: dict[str, Any]) -> str:
    lines = [f"impact {report['path']}（域：{report['domain']}）"]
    if report.get("chapter"):
        lines.append(f"  章节：{report['chapter']}")
    if report.get("affected_chapters"):
        lines.append("  受影响章：" + "、".join(str(c) for c in report["affected_chapters"]))
    for impact in report.get("impacts") or []:
        lines.append(f"  影响：{impact}")
    for suggestion in report.get("suggestions") or []:
        lines.append(f"  建议：{suggestion}")
    for option in report.get("options") or []:
        lines.append(f"  {option}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="影响反查（impact，只读）")
    parser.add_argument("--path", required=True, help="书仓内相对路径")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    report = analyze_impact(args.project_root, args.path)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_impact_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
