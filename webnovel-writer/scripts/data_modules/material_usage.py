"""素材使用轨迹与写作接线（webnovel-copilot-300 · M2/T12，流程 F-05/F-11）。

- `素材/使用轨迹.jsonl`：一行一次消费，append-only（残行容错），schema 见
  docs/zcode/webnovel-copilot-300/06-data-design.md §1。
- 消费来源：章纲卡 front matter 的 `素材引用`（`表:ID`，裸 ID 全表反查）。
- `定版版本`：条目在最新定版快照中 → `v{NN}`；仅在活层 → `live`。
- `log_chapter_materials`：一章一批轨迹（重复落账拒绝）；`settle_materials_for_chapter`
  供 chapter-commit 在 projections 后调用——失败静默，绝不阻断写章事务。
红线：只追加不修改历史行；引用缺失只告警不落账、不阻断。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .author_journal import append_events
from .chapter_outline_batch import parse_chapter_card
from .material_store import (
    MATERIAL_TABLES,
    _read_csv_rows,
    latest_frozen_version,
    material_csv_path,
    normalize_table,
    read_frozen_table,
)

TRAJECTORY_SCHEMA_VERSION = "material-usage/1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def trajectory_path(project_root: str | Path) -> Path:
    return Path(project_root) / "素材" / "使用轨迹.jsonl"


def read_trajectory(project_root: str | Path, *, chapter: int | None = None) -> list[dict[str, Any]]:
    """读使用轨迹（残行忽略；chapter 过滤时不含 ts 缺失行判定）。"""
    path = trajectory_path(project_root)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if chapter is None or row.get("章") == int(chapter):
                rows.append(row)
    return rows


def append_usage(project_root: str | Path, chapter: int, entries: list[dict[str, Any]]) -> int:
    """追加一章的轨迹行（条目顺序即章纲卡引用顺序）。返回写入行数。"""
    path = trajectory_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = _utc_now_iso()
    with path.open("a", encoding="utf-8", newline="\n") as file:
        for entry in entries:
            row = {
                "schema_version": TRAJECTORY_SCHEMA_VERSION,
                "ts": ts,
                "章": int(chapter),
                "条目id": str(entry.get("条目id") or ""),
                "定版版本": str(entry.get("定版版本") or "live"),
                "用法": str(entry.get("用法") or "章纲引用"),
            }
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(entries)


def resolve_ref(project_root: str | Path, ref: str) -> dict[str, Any]:
    """解析素材引用 `表:ID`（裸 ID 按 MATERIAL_TABLES 顺序全表反查）。

    判定优先级：活层（live）→ 最新定版（v{NN}）→ 未找到。
    """
    ref = str(ref).strip()
    if ":" in ref:
        raw_table, _, entry_id = ref.partition(":")
        entry_id = entry_id.strip()
        table = normalize_table(raw_table)
        if table is None:
            return {"ok": False, "ref": ref, "reason": "unknown_table", "table": raw_table}
        candidates = [(table, entry_id)]
    else:
        entry_id = ref
        candidates = [(table, entry_id) for table in MATERIAL_TABLES]

    root = Path(project_root)
    for table, current_id in candidates:
        live_path = material_csv_path(root, table)
        if live_path.is_file() and any(row.get("id") == current_id for row in _read_csv_rows(live_path)):
            return {"ok": True, "table": table, "id": current_id, "version": "live"}
        frozen_version = latest_frozen_version(root)
        if frozen_version is not None:
            frozen = read_frozen_table(root, table, frozen_version)
            if any(row.get("id") == current_id for row in frozen):
                return {"ok": True, "table": table, "id": current_id, "version": f"v{frozen_version:02d}"}
    return {"ok": False, "ref": ref, "reason": "not_found"}


def log_chapter_materials(
    project_root: str | Path,
    chapter: int,
    *,
    usage: str = "章纲引用",
    force: bool = False,
) -> dict[str, Any]:
    """消费章纲卡素材引用 → 轨迹落账 + journal(settle)。

    一章一批：已有本章轨迹且未 force → already_logged（幂等闸）。
    """
    root = Path(project_root)
    if not force and read_trajectory(root, chapter=chapter):
        return {"ok": False, "error": "already_logged", "chapter": int(chapter)}

    card_path = root / "大纲" / "章纲" / f"{int(chapter):04d}.md"
    if not card_path.is_file():
        return {"ok": False, "error": "card_missing", "chapter": int(chapter)}
    fields, _ = parse_chapter_card(card_path.read_text(encoding="utf-8"))
    refs = fields.get("素材引用") or []
    if isinstance(refs, str):
        refs = [refs]

    logged: list[dict[str, Any]] = []
    missing: list[str] = []
    for ref in refs:
        resolved = resolve_ref(root, str(ref))
        if resolved["ok"]:
            logged.append({"ref": str(ref), "table": resolved["table"], "条目id": resolved["id"], "定版版本": resolved["version"]})
        else:
            missing.append(str(ref))

    append_usage(root, chapter, [
        {"条目id": item["条目id"], "定版版本": item["定版版本"], "用法": usage} for item in logged
    ])
    append_events(
        root,
        [
            {
                "actor": "system",
                "action": "settle",
                "domain": "素材",
                "path": f"大纲/章纲/{int(chapter):04d}.md",
                "change_kind": "structure",
                "diff_stat": {"ins": len(logged), "del": 0},
                "summary": f"章 {int(chapter)} 素材引用落账 {len(logged)} 条" + (f"（缺失 {len(missing)}）" if missing else ""),
                "impact": [],
            }
        ],
    )
    return {
        "ok": True,
        "schema_version": TRAJECTORY_SCHEMA_VERSION,
        "chapter": int(chapter),
        "logged": logged,
        "missing": missing,
    }


def settle_materials_for_chapter(project_root: str | Path, chapter: int) -> bool:
    """chapter-commit 落账钩子：成功 True；无卡/重复/异常一律 False（静默，不阻断写章事务）。"""
    try:
        report = log_chapter_materials(project_root, chapter)
    except Exception:
        return False
    return bool(report.get("ok"))


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python -X utf8 material_usage.py {log|trajectory} [options]

    一般经 `webnovel.py materials log|trajectory` 调用。
    """
    import argparse

    parser = argparse.ArgumentParser(description="素材使用轨迹（T12）")
    parser.add_argument("action", choices=["log", "trajectory"])
    parser.add_argument("--chapter", type=int, default=None)
    parser.add_argument("--usage", default="章纲引用")
    parser.add_argument("--force", action="store_true", help="log 重复落账覆盖幂等闸（追加第二批）")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    if args.action == "log":
        if args.chapter is None:
            parser.error("log 需要 --chapter")
        report = log_chapter_materials(root, args.chapter, usage=args.usage, force=args.force)
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            if not report.get("ok"):
                print(f"ERROR {report.get('error')}（章 {report.get('chapter')}）")
            else:
                print(f"OK 章 {report['chapter']} 落账 {len(report['logged'])} 条")
                for item in report["logged"]:
                    print(f"  {item['ref']} → {item['定版版本']}")
                for ref in report["missing"]:
                    print(f"  WARN 缺失引用: {ref}")
        return 0 if report.get("ok") else 1

    rows = read_trajectory(root, chapter=args.chapter)
    if args.format == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(f"章{row.get('章')}  {row.get('条目id')}  {row.get('定版版本')}  {row.get('用法')}")
        if not rows:
            print("(无轨迹记录)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
