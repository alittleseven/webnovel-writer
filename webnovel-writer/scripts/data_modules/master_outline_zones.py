"""总纲三区结构与自动分区迁移（webnovel-copilot-300 · M1/T6，流程 F-02）。

三区约定（05 §2.1）——增量叠加在既有总纲尾部，书级主体原样保留（红线）：
- 甲区 · 已写卷详案（冻结区）：全部章节已定稿的卷，指向卷纲文件并标记冻结状态；
- 乙区 · 当前卷活跃区：正在写的卷（部分完成或首个未开始卷），regen 只作用于本区；
- 丙区 · 未来卷锚点：每卷一行锚点（≤10 行约定），开卷时走锚点扩写（画廊）。

卷分类按定稿正文完成度：卷范围内章节全部有 定稿/正文/NNNN-*.md = 已写；
部分有 = 活跃；无 = 锚点（首卷无章节时首卷为活跃）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

ZONES_SCHEMA_VERSION = "zones/1"

MASTER_OUTLINE_REL = Path("大纲") / "总纲.md"
VOLUME_OUTLINE_DIR = Path("大纲") / "卷纲"
FINALIZED_TEXT_DIR = Path("定稿") / "正文"

ZONE_A_MARKER = "<!-- zone:A frozen -->"
ZONE_B_MARKER = "<!-- zone:B active -->"
ZONE_C_MARKER = "<!-- zone:C anchor -->"
ZONE_A_HEADING = "## 甲区 · 已写卷详案（冻结区）"
ZONE_B_HEADING = "## 乙区 · 当前卷活跃区"
ZONE_C_HEADING = "## 丙区 · 未来卷锚点"

_VOLUME_RANGE_RE = re.compile(r"第(\d+)-(\d+)章")
_FINALIZED_CHAPTER_RE = re.compile(r"^(\d{4})-")
_VOLUME_FILE_RE = re.compile(r"^第(\d+)卷\.md$")


def _master_outline_path(project_root: str | Path) -> Path:
    return Path(project_root) / MASTER_OUTLINE_REL


def has_zones(text: str) -> bool:
    return all(marker in text for marker in (ZONE_A_MARKER, ZONE_B_MARKER, ZONE_C_MARKER))


def parse_zones(text: str) -> dict[str, str] | None:
    """按标记切分三区；未迁移返回 None。"""
    if not has_zones(text):
        return None
    # 顺序：book_level | A | B | C
    parts = re.split(
        re.escape(ZONE_A_MARKER) + r"|" + re.escape(ZONE_B_MARKER) + r"|" + re.escape(ZONE_C_MARKER),
        text,
    )
    if len(parts) != 4:
        return None
    return {
        "book_level": parts[0].strip("\n"),
        "zone_a": parts[1].strip("\n"),
        "zone_b": parts[2].strip("\n"),
        "zone_c": parts[3].strip("\n"),
    }


def extract_volume_plan_rows(text: str) -> list[dict[str, str]]:
    """解析 `## 卷划分` 表格（| 卷号 | 卷名 | 章节范围 | 核心冲突 | 卷末高潮 |）。"""
    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip().startswith("## 卷划分"))
    except StopIteration:
        return []
    header_idx = None
    for i in range(start + 1, len(lines)):
        if lines[i].strip().startswith("|") and "卷号" in lines[i]:
            header_idx = i
            break
    if header_idx is None:
        return []
    rows: list[dict[str, str]] = []
    for ln in lines[header_idx + 2 :]:  # 跳过表头与分隔行
        stripped = ln.strip()
        if not stripped.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 5 or not cells[0].isdigit():
            continue
        rows.append(
            {
                "卷号": cells[0],
                "卷名": cells[1],
                "章节范围": cells[2],
                "核心冲突": cells[3],
                "卷末高潮": cells[4],
            }
        )
    return rows


def _finalized_chapters(project_root: str | Path) -> set[int]:
    root = Path(project_root)
    chapters: set[int] = set()
    text_dir = root / FINALIZED_TEXT_DIR
    if not text_dir.is_dir():
        return chapters
    for file in text_dir.iterdir():
        match = _FINALIZED_CHAPTER_RE.match(file.name)
        if match:
            chapters.add(int(match.group(1)))
    return chapters


def _volume_outline_file(project_root: str | Path, volume_no: int) -> str:
    return f"卷纲/第{volume_no:02d}卷.md"


def classify_volumes(project_root: str | Path, rows: list[dict[str, str]]) -> dict[str, str]:
    """卷分类：written / active / anchor（按定稿完成度）。"""
    root = Path(project_root)
    finalized = _finalized_chapters(root)
    classification: dict[str, str] = {}
    for row in rows:
        match = _VOLUME_RANGE_RE.search(row.get("章节范围", ""))
        if not match:
            classification[row["卷号"]] = "anchor"
            continue
        start, end = int(match.group(1)), int(match.group(2))
        present = [c for c in range(start, end + 1) if c in finalized]
        if len(present) == end - start + 1:
            classification[row["卷号"]] = "written"
        elif present:
            classification[row["卷号"]] = "active"
        else:
            classification[row["卷号"]] = "anchor"
    # 无活跃卷时（全锚点或全已写），首个非已写卷设为活跃
    if "active" not in classification.values():
        for row in rows:
            if classification.get(row["卷号"]) != "written":
                classification[row["卷号"]] = "active"
                break
    return classification


def _zone_blocks(project_root: str | Path, rows: list[dict[str, str]], classification: dict[str, str]) -> str:
    root = Path(project_root)
    written_lines: list[str] = []
    active_lines: list[str] = []
    anchor_lines: list[str] = []
    for row in rows:
        volume_no = int(row["卷号"])
        status = classification[row["卷号"]]
        pointer = _volume_outline_file(root, volume_no)
        pointer_exists = (root / VOLUME_OUTLINE_DIR / f"第{volume_no:02d}卷.md").is_file()
        pointer_part = f"详案：{pointer}" if pointer_exists else "（详案待生成）"
        line = f"- 卷 {row['卷号']} 《{row['卷名']}》 {row['章节范围']}：{row['核心冲突']} → {row['卷末高潮']}｜{pointer_part}"
        if status == "written":
            written_lines.append(line.replace("｜", "｜冻结：", 1))
        elif status == "active":
            active_lines.append(line + "（活跃：regen 只作用于本区）")
        else:
            anchor_lines.append(f"- 卷 {row['卷号']} 《{row['卷名']}》 {row['章节范围']}：{row['核心冲突']} → {row['卷末高潮']}")

    blocks = [
        ZONE_A_MARKER + "\n" + ZONE_A_HEADING + "\n\n" + ("\n".join(written_lines) or "- （暂无——首卷进行中）") + "\n",
        ZONE_B_MARKER + "\n" + ZONE_B_HEADING + "\n\n" + ("\n".join(active_lines) or "- （无）") + "\n",
        ZONE_C_MARKER + "\n" + ZONE_C_HEADING + "\n\n" + ("\n".join(anchor_lines) or "- （无）") + "\n",
    ]
    return "\n\n".join(blocks)


def migrate_to_zones(project_root: str | Path, *, dry_run: bool = False) -> dict[str, Any]:
    """首次运行自动分区迁移（幂等；红线：书级主体原样保留）。"""
    path = _master_outline_path(project_root)
    if not path.is_file():
        return {"ok": False, "migrated": False, "error": f"missing {MASTER_OUTLINE_REL}"}
    text = path.read_text(encoding="utf-8")
    if has_zones(text):
        return {"ok": True, "migrated": False, "reason": "already_zoned"}

    rows = extract_volume_plan_rows(text)
    if not rows:
        return {"ok": False, "migrated": False, "error": "总纲缺少 ## 卷划分 表格，无法分区"}

    classification = classify_volumes(project_root, rows)
    written = [row["卷号"] for row in rows if classification[row["卷号"]] == "written"]
    active = [row["卷号"] for row in rows if classification[row["卷号"]] == "active"]

    new_text = text.rstrip("\n") + "\n\n" + _zone_blocks(project_root, rows, classification) + "\n"
    if not dry_run:
        path.write_text(new_text, encoding="utf-8", newline="\n")

    return {
        "ok": True,
        "migrated": True,
        "schema_version": ZONES_SCHEMA_VERSION,
        "classification": classification,
        "written_volumes": written,
        "active_volume": active[0] if active else None,
        "dry_run": dry_run,
    }


def zone_state(project_root: str | Path) -> dict[str, Any]:
    """三区状态（只读）。"""
    path = _master_outline_path(project_root)
    if not path.is_file():
        return {"ok": False, "has_zones": False, "error": f"missing {MASTER_OUTLINE_REL}"}
    zones = parse_zones(path.read_text(encoding="utf-8"))
    if zones is None:
        return {"ok": True, "has_zones": False}
    rows = extract_volume_plan_rows(zones["book_level"])
    classification = classify_volumes(project_root, rows)
    active = [v for v, s in classification.items() if s == "active"]
    return {
        "ok": True,
        "has_zones": True,
        "schema_version": ZONES_SCHEMA_VERSION,
        "classification": classification,
        "active_volume": active[0] if active else None,
        "written_volumes": [v for v, s in classification.items() if s == "written"],
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="总纲三区结构（T6）")
    parser.add_argument("action", choices=["migrate", "show"])
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    if args.action == "migrate":
        report = migrate_to_zones(root, dry_run=args.dry_run)
    else:
        report = zone_state(root)

    if args.format == "json":
        print(_json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if args.action == "migrate":
            if not report.get("ok"):
                print(f"ERROR zones migrate: {report.get('error')}")
            elif report.get("migrated"):
                print(f"OK zones migrate: active=卷{report.get('active_volume')} written={report.get('written_volumes')}")
            else:
                print("OK zones migrate: 已是三区结构，跳过")
        else:
            if not report.get("has_zones"):
                print("总纲尚未迁移三区（运行 zones migrate）")
            else:
                print(f"active=卷{report.get('active_volume')} written={report.get('written_volumes')}")
                for volume, status in (report.get("classification") or {}).items():
                    print(f"  卷{volume}: {status}")
    return 0 if report.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
