"""信息差与知识边界（webnovel-copilot-300 · M4/T21，06 §9 / A1）。

`设定/信息差.md` 是「谁知道什么」的条目表（信息点/知晓者/知晓章/泄露禁忌），
消费方：reviewer 知识边界维的证据源（reviewer.md §6 指引 `knowledge boundary`
取数后逐条核对）、knowledge 查询（A1：该实体每个信息点——哪些角色知道、从哪章知道）。

boundary(chapter) 输出：
- `facts`：每个信息点 + 该章是否已知晓（知晓章 ≤ chapter）；
- `unknown_at_chapter`：本章尚未揭晓的信息点——正文出现角色使用即为知识边界违例；
- `entity` 过滤：只保留该实体作为知晓者的信息点（A1 口径）。
文件缺失优雅降级（facts 空 + note），不算失败。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

INFO_GAP_SCHEMA_VERSION = "info-gap/1"
INFO_GAP_REL = Path("设定") / "信息差.md"
_KNOWER_SPLIT_RE = re.compile(r"[、，,;；\s]+")


def info_gap_path(project_root: str | Path) -> Path:
    candidates = [Path(project_root) / "定稿" / "设定" / "信息差.md", Path(project_root) / "设定" / "信息差.md", Path(project_root) / "设定集" / "信息差.md"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return Path(project_root) / INFO_GAP_REL


def parse_info_gap(project_root: str | Path) -> list[dict[str, Any]]:
    """解析信息差表（缺失返回 []；残行/缺列行忽略）。"""
    path = info_gap_path(project_root)
    if not path.is_file():
        return []
    facts: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4 or set(cells[0]) <= {"-", " "} or cells[0] == "信息点":
            continue
        try:
            chapter = int(re.sub(r"[^\d]", "", cells[2]) or 0)
        except ValueError:
            continue
        facts.append(
            {
                "信息点": cells[0],
                "知晓者": [name for name in _KNOWER_SPLIT_RE.split(cells[1]) if name],
                "知晓章": chapter,
                "泄露禁忌": cells[3],
            }
        )
    return facts


def boundary(project_root: str | Path, *, chapter: int, entity: str | None = None) -> dict[str, Any]:
    """知识边界证据（reviewer A1/A1 取数口）：按章输出信息点知晓状态。"""
    facts = parse_info_gap(project_root)
    if entity:
        facts = [fact for fact in facts if entity in fact["知晓者"]]
    enriched: list[dict[str, Any]] = []
    unknown: list[str] = []
    for fact in facts:
        known = int(chapter) >= int(fact["知晓章"])
        enriched.append({**fact, "该章已知": known})
        if not known:
            unknown.append(fact["信息点"])
    note = "" if facts else "信息差.md 未建立（设定域 advisory 文件，建议 /webnovel:init 后补齐）"
    return {
        "ok": True,
        "schema_version": INFO_GAP_SCHEMA_VERSION,
        "chapter": int(chapter),
        "entity": entity or "",
        "facts": enriched,
        "unknown_at_chapter": unknown,
        "note": note,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python -X utf8 info_gap.py boundary --chapter N [--entity 名]

    一般经 `webnovel.py knowledge boundary` 调用（A1）。
    """
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="信息差与知识边界（T21）")
    parser.add_argument("action", choices=["boundary"])
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--entity", default="")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="json")
    args = parser.parse_args(argv)

    report = boundary(Path(args.project_root), chapter=args.chapter, entity=args.entity or None)
    if args.format == "json":
        print(_json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"信息差边界（第 {report['chapter']} 章口径）：")
    for fact in report["facts"]:
        state = "已知" if fact["该章已知"] else "未知"
        taboo = f"｜禁忌 {fact['泄露禁忌']}" if fact["泄露禁忌"] else ""
        print(f"  [{state}] {fact['信息点']}（知晓者 {'、'.join(fact['知晓者'])}，自第 {fact['知晓章']} 章）{taboo}")
    if report["note"]:
        print(f"NOTE {report['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
