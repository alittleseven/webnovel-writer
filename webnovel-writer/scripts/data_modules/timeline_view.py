"""卷纲时间线视图（webnovel-copilot-300 · M1/T9，流程 F-03）。

- build：章纲卡（卷内）按章排序导出为可解析表格 `大纲/卷纲/第NN卷-时间线.md`；
  列 = 章 | 故事内时间 | 事件（节点） | 伏笔/承诺 | 战力事件；重复时间锚入 warnings。
- sync：作者直接编辑视图后，反向对账回章纲卡时间锚——dry-run 只列 diff，
  `--apply`（apply=True）才回写（P1：作者确认后才动卡）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .author_journal import append_events
from .chapter_outline_batch import parse_chapter_card

TIMELINE_SCHEMA_VERSION = "timeline-view/1"

_VOLUME_DIR = Path("大纲") / "卷纲"
_VIEW_HEADER_RE = re.compile(r"^<!-- timeline-view: v1 volume=(\d+)")
_TABLE_ROW_RE = re.compile(r"^\|\s*(\d{1,4})\s*\|\s*(.*?)\s*\|")


def _view_path(project_root: str | Path, volume: int) -> Path:
    return Path(project_root) / _VOLUME_DIR / f"第{volume:02d}卷-时间线.md"


def _cards_of_volume(project_root: str | Path, volume: int) -> list[tuple[int, dict[str, Any]]]:
    chapter_dir = Path(project_root) / "大纲" / "章纲"
    if not chapter_dir.is_dir():
        return []
    cards: list[tuple[int, dict[str, Any]]] = []
    for file in chapter_dir.glob("*.md"):
        match = re.fullmatch(r"(\d{1,4})", file.stem)
        if not match:
            continue
        fields, _ = parse_chapter_card(file.read_text(encoding="utf-8"))
        try:
            card_volume = int(str(fields.get("卷") or "0"))
        except ValueError:
            card_volume = 0
        if card_volume != volume:
            continue
        cards.append((int(match.group(1)), fields))
    return sorted(cards, key=lambda item: item[0])


def _join(values: Any) -> str:
    if not values:
        return "—"
    if isinstance(values, list):
        return "；".join(str(v) for v in values)
    return str(values)


def build_timeline_view(project_root: str | Path, *, volume: int) -> dict[str, Any]:
    cards = _cards_of_volume(project_root, volume)
    warnings: list[str] = []
    rows: list[list[str]] = []
    seen_anchors: dict[str, int] = {}
    for chapter, fields in cards:
        anchor = str(fields.get("时间锚") or "—")
        if anchor != "—" and anchor in seen_anchors:
            warnings.append(f"章{chapter} 时间锚 '{anchor}' 与章{seen_anchors[anchor]} 重复")
        else:
            seen_anchors[anchor] = chapter
        rows.append(
            [
                str(chapter),
                anchor,
                _join(fields.get("节点")),
                _join(fields.get("承诺推进")),
                _join(fields.get("战力事件")),
            ]
        )

    import datetime as _dt

    header = (
        f"<!-- timeline-view: v1 volume={volume} generated={_dt.datetime.now().astimezone().isoformat(timespec='seconds')} -->\n"
        f"# 第 {volume} 卷 · 时间线视图\n\n"
        "> 本视图由章纲卡导出；作者直接修改本表后运行 `webnovel.py timeline sync` 可把时间锚回写章纲卡。\n\n"
    )
    if not rows:
        header += "> 暂无章纲卡（本卷）\n\n"
    table = "| 章 | 故事内时间 | 事件（节点） | 伏笔/承诺 | 战力事件 |\n|---|---|---|---|---|\n"
    for row in rows:
        table += "| " + " | ".join(row) + " |\n"

    _view_path(project_root, volume).parent.mkdir(parents=True, exist_ok=True)
    _view_path(project_root, volume).write_text(header + table, encoding="utf-8", newline="\n")

    return {
        "ok": True,
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "volume": volume,
        "rows": len(rows),
        "warnings": warnings,
        "view_path": str(_view_path(project_root, volume)),
    }


def _parse_view_anchors(view_text: str) -> dict[int, str]:
    anchors: dict[int, str] = {}
    in_table = False
    for line in view_text.splitlines():
        if line.strip().startswith("|") and "章" in line and "故事内时间" in line:
            in_table = True
            continue
        if in_table and line.strip().startswith("|---"):
            continue
        if in_table:
            match = _TABLE_ROW_RE.match(line.strip())
            if not match:
                continue
            anchor = match.group(2).strip()
            if anchor and anchor != "—":
                anchors[int(match.group(1))] = anchor
    return anchors


def sync_view_to_cards(project_root: str | Path, *, volume: int, dry_run: bool = True) -> dict[str, Any]:
    """视图 → 章纲卡时间锚对账（作者确认语义：dry_run 默认）。"""
    view_path = _view_path(project_root, volume)
    if not view_path.is_file():
        return {"ok": True, "diffs": [], "applied": 0, "reason": "view_missing"}
    view_anchors = _parse_view_anchors(view_path.read_text(encoding="utf-8"))

    diffs: list[dict[str, Any]] = []
    chapter_dir = Path(project_root) / "大纲" / "章纲"
    for chapter, new_anchor in sorted(view_anchors.items()):
        card_path = chapter_dir / f"{chapter:04d}.md"
        if not card_path.is_file():
            continue
        fields, body = parse_chapter_card(card_path.read_text(encoding="utf-8"))
        old_anchor = str(fields.get("时间锚") or "")
        if old_anchor and old_anchor != new_anchor:
            diffs.append({"chapter": chapter, "old": old_anchor, "new": new_anchor})
            if not dry_run:
                text = card_path.read_text(encoding="utf-8")
                text = text.replace(f"时间锚: {old_anchor}", f"时间锚: {new_anchor}", 1)
                card_path.write_text(text, encoding="utf-8", newline="\n")
                append_events(
                    project_root,
                    [
                        {
                            "actor": "author",
                            "action": "edit",
                            "domain": "章纲",
                            "path": f"大纲/章纲/{chapter:04d}.md",
                            "change_kind": "fact",
                            "diff_stat": {"ins": 1, "del": 1},
                            "summary": f"时间线视图回写：时间锚 {old_anchor}→{new_anchor}",
                            "impact": [f"context-stale:{chapter:04d}"],
                        }
                    ],
                )

    return {
        "ok": True,
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "diffs": diffs,
        "applied": 0 if dry_run else len(diffs),
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="卷纲时间线视图（T9）")
    parser.add_argument("action", choices=["build", "sync"])
    parser.add_argument("--volume", type=int, required=True, help="卷号")
    parser.add_argument("--apply", action="store_true", help="sync 时回写章纲卡（默认 dry-run）")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    if args.action == "build":
        report = build_timeline_view(root, volume=args.volume)
    else:
        report = sync_view_to_cards(root, volume=args.volume, dry_run=not args.apply)

    if args.format == "json":
        print(_json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if args.action == "build":
            print(f"OK timeline build: {report['rows']} 行 → {report['view_path']}")
            for warning in report.get("warnings") or []:
                print(f"  WARN {warning}")
        else:
            diffs = report.get("diffs") or []
            if not diffs:
                print("OK timeline sync: 无差异" if report.get("reason") is None else f"OK（{report.get('reason')}）")
            else:
                mode = "applied" if report.get("applied") else "dry-run"
                print(f"{mode}: {len(diffs)} 处时间锚差异")
                for diff in diffs:
                    print(f"  章{diff['chapter']}: {diff['old']} → {diff['new']}")
    return 0 if report.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
