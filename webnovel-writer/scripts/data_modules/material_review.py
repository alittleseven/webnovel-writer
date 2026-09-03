"""material-review 素材卷审（webnovel-copilot-300 · M2/T14，流程 F-06）。

三步：①脚本统计（0 token：使用率/最近使用章/来源分布/衰减标记）→
②建议（合并候选由确定性规则给出；同义合并/淘汰/缺口的 LLM 建议在会话侧）→
③作者逐项裁决，`apply_rulings` 执行 archive/delete/merge 并留 journal。

衰减规则：`状态=active` 且最近 N 卷未使用（章→卷换算 = (章-1)//卷规模 + 1，
卷规模优先取 book.yaml `卷规模`，缺省 50）；从未使用且当前卷号 > N 也计衰减。
红线：裁决只动活层行（归档保留数据），定版快照不受影响。
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .author_journal import append_events
from .material_store import MATERIAL_TABLES, _read_csv_rows, material_csv_path

REVIEW_SCHEMA_VERSION = "material-review/1"
DEFAULT_CHAPTERS_PER_VOLUME = 50
VALID_ACTIONS = ("archive", "delete", "merge")


def _chapters_per_volume(project_root: Path) -> int:
    book_yaml = project_root / "book.yaml"
    if book_yaml.is_file():
        match = re.search(r"^卷规模:\s*(\d+)", book_yaml.read_text(encoding="utf-8"), re.MULTILINE)
        if match:
            return int(match.group(1))
    return DEFAULT_CHAPTERS_PER_VOLUME


def _volume_of(chapter: int, chapters_per_volume: int) -> int:
    return (int(chapter) - 1) // max(chapters_per_volume, 1) + 1


def review_stats(
    project_root: str | Path,
    *,
    current_volume: int | None = None,
    chapters_per_volume: int | None = None,
    decay_volumes: int = 1,
) -> dict[str, Any]:
    """全表逐条统计（含归档行，裁决需要看见全貌）。"""
    from .material_usage import read_trajectory

    root = Path(project_root)
    cpv = chapters_per_volume or _chapters_per_volume(root)
    usage: dict[str, list[int]] = {}
    for row in read_trajectory(root):
        entry_id = row.get("条目id", "")
        if entry_id:
            usage.setdefault(entry_id, []).append(int(row.get("章", 0)))

    entries: list[dict[str, Any]] = []
    source_distribution: dict[str, int] = {}
    for table in MATERIAL_TABLES:
        for row in _read_csv_rows(material_csv_path(root, table)):
            source = row.get("来源", "")
            if source:
                source_distribution[source] = source_distribution.get(source, 0) + 1
            chapters = usage.get(row.get("id", ""), [])
            last_chapter = max(chapters) if chapters else None
            decayed = False
            if row.get("状态", "active") == "active" and current_volume is not None:
                if last_chapter is None:
                    decayed = current_volume > decay_volumes
                else:
                    decayed = _volume_of(last_chapter, cpv) < current_volume - decay_volumes + 1
            entries.append(
                {
                    "table": table,
                    "id": row.get("id", ""),
                    "名称": row.get("名称", ""),
                    "来源": source,
                    "状态": row.get("状态", "") or "active",
                    "uses": len(chapters),
                    "last_chapter": last_chapter,
                    "decayed": decayed,
                }
            )
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "entries": entries,
        "total": len(entries),
        "source_distribution": source_distribution,
        "chapters_per_volume": cpv,
        "current_volume": current_volume,
        "decay_volumes": int(decay_volumes),
    }


def review_candidates(
    project_root: str | Path,
    *,
    current_volume: int | None = None,
    decay_volumes: int = 1,
) -> dict[str, Any]:
    """确定性候选：衰减 → 归档候选；同表同名 → 合并候选（LLM 建议在会话侧补充）。"""
    stats = review_stats(project_root, current_volume=current_volume, decay_volumes=decay_volumes)
    archive_candidates = [
        {"table": s["table"], "id": s["id"], "名称": s["名称"], "reason": "衰减（长期未使用）"}
        for s in stats["entries"]
        if s["decayed"]
    ]

    by_name: dict[tuple[str, str], list[str]] = {}
    for s in stats["entries"]:
        if s["状态"] == "active":
            by_name.setdefault((s["table"], s["名称"].strip()), []).append(s["id"])
    merge_candidates = [
        {"table": table, "ids": ids, "名称": name}
        for (table, name), ids in sorted(by_name.items())
        if len(ids) > 1
    ]
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "archive_candidates": archive_candidates,
        "merge_candidates": merge_candidates,
        "current_volume": current_volume,
    }


def apply_rulings(project_root: str | Path, rulings: list[dict[str, Any]]) -> dict[str, Any]:
    """执行裁决：archive（状态→归档+备注）/ delete（删行）/ merge（并入目标行）。

    返回 {ok, applied, missing, skipped}；任一裁决非法整体拒绝（不产生半截写入）。
    """
    for ruling in rulings:
        if ruling.get("action") not in VALID_ACTIONS:
            return {"ok": False, "error": "invalid_action", "ruling": ruling}
        if ruling.get("action") == "merge" and not ruling.get("merge_into"):
            return {"ok": False, "error": "merge_requires_target", "ruling": ruling}

    root = Path(project_root)
    # 按表聚合加载（一次读一表，行内改写）
    tables: dict[str, list[dict[str, str]]] = {}
    headers: dict[str, list[str]] = {}
    applied = 0
    missing: list[str] = []
    skipped: list[dict[str, str]] = []
    summaries: list[str] = []

    def _rows(table: str) -> list[dict[str, str]]:
        if table not in tables:
            path = material_csv_path(root, table)
            tables[table] = _read_csv_rows(path)
            if path.is_file():
                with path.open("r", encoding="utf-8-sig", newline="") as f:
                    headers[table] = list(csv.DictReader(f).fieldnames or [])
        return tables[table]

    for ruling in rulings:
        table, action = ruling["table"], ruling["action"]
        entry_id = str(ruling.get("id", ""))
        rows = _rows(table)
        index = next((i for i, row in enumerate(rows) if row.get("id") == entry_id), None)
        if index is None:
            missing.append(f"{table}:{entry_id}")
            continue
        reason = str(ruling.get("reason", "") or "")
        if action == "archive":
            rows[index]["状态"] = "归档"
            rows[index]["备注"] = _append_note(rows[index].get("备注", ""), reason or "material-review 归档")
            applied += 1
            summaries.append(f"{table}:{entry_id} 归档")
        elif action == "delete":
            rows.pop(index)
            applied += 1
            summaries.append(f"{table}:{entry_id} 删除")
        else:  # merge
            target_id = str(ruling["merge_into"])
            t_index = next((i for i, row in enumerate(rows) if row.get("id") == target_id and i != index), None)
            if t_index is None:
                skipped.append({"id": entry_id, "reason": f"merge 目标不存在: {target_id}"})
                continue
            rows[index]["状态"] = "归档"
            rows[index]["备注"] = _append_note(rows[index].get("备注", ""), f"并入:{target_id}")
            rows[t_index]["备注"] = _append_note(rows[t_index].get("备注", ""), f"并入自:{entry_id}")
            applied += 1
            summaries.append(f"{table}:{entry_id} 并入 {target_id}")

    for table, rows in tables.items():
        path = material_csv_path(root, table)
        if not rows and not path.is_file():
            continue
        fieldnames = headers.get(table) or (list(rows[0].keys()) if rows else [])
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    if applied:
        append_events(
            root,
            [
                {
                    "actor": "author",
                    "action": "edit",
                    "domain": "素材",
                    "path": "素材/活/",
                    "change_kind": "structure",
                    "diff_stat": {"ins": 0, "del": applied},
                    "summary": f"material-review 裁决执行 {applied} 项：{'；'.join(summaries)}",
                    "impact": [],
                }
            ],
        )
    return {
        "ok": True,
        "schema_version": REVIEW_SCHEMA_VERSION,
        "applied": applied,
        "missing": missing,
        "skipped": skipped,
        "summaries": summaries,
    }


def _append_note(note: str, addition: str) -> str:
    note = (note or "").strip()
    if not addition:
        return note
    return f"{note}；{addition}" if note else addition


def parse_ruling(raw: str) -> dict[str, Any]:
    """解析 `表:ID:动作[:并入ID[:理由]]` 字符串为裁决 dict。"""
    parts = [p.strip() for p in raw.split(":") if p.strip()]
    ruling: dict[str, Any] = {"table": parts[0] if parts else "", "id": parts[1] if len(parts) > 1 else "", "action": parts[2] if len(parts) > 2 else ""}
    if len(parts) > 3:
        if parts[2] == "merge":
            ruling["merge_into"] = parts[3]
            if len(parts) > 4:
                ruling["reason"] = parts[4]
        else:
            ruling["reason"] = parts[3]
    return ruling


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python -X utf8 material_review.py {review|apply-ruling} [options]

    一般经 `webnovel.py materials review|apply-ruling` 调用。
    """
    import argparse

    parser = argparse.ArgumentParser(description="material-review 素材卷审（T14）")
    parser.add_argument("action", choices=["review", "apply-ruling"])
    parser.add_argument("--volume", type=int, default=None, help="当前卷号（衰减计算输入）")
    parser.add_argument("--decay-volumes", type=int, default=1, help="N 卷未用记衰减（默认 1）")
    parser.add_argument("--ruling", action="append", default=[], help="裁决 表:ID:动作[:并入ID[:理由]]（可重复）")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    if args.action == "review":
        stats = review_stats(root, current_volume=args.volume, decay_volumes=args.decay_volumes)
        candidates = review_candidates(root, current_volume=args.volume, decay_volumes=args.decay_volumes)
        report = {"ok": True, **stats, "archive_candidates": candidates["archive_candidates"], "merge_candidates": candidates["merge_candidates"]}
    else:
        if not args.ruling:
            parser.error("apply-ruling 需要 --ruling")
        report = apply_rulings(root, rulings=[parse_ruling(raw) for raw in args.ruling])

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok", True) else 1

    if args.action == "review":
        print(f"素材统计：{report['total']} 条；来源分布 {report['source_distribution']}")
        for s in report["entries"]:
            decay_mark = " 衰减" if s["decayed"] else ""
            last = f"章{s['last_chapter']}" if s["last_chapter"] is not None else "未用"
            print(f"  {s['table']}:{s['id']}  {s['名称']}  用{s['uses']}次/最近{last}  [{s['来源']}]{decay_mark}")
        for c in report["merge_candidates"]:
            print(f"  合并候选 {'='.join(c['ids'])}（{c['名称']}）")
    else:
        if not report.get("ok"):
            print(f"ERROR {report.get('error')}")
            return 1
        print(f"OK 裁决执行 {report['applied']} 项")
        for summary in report["summaries"]:
            print(f"  {summary}")
        for item in report["missing"]:
            print(f"  MISS {item}")
        for item in report["skipped"]:
            print(f"  SKIP {item['id']}（{item['reason']}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
