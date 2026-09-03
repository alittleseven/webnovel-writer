"""素材入库三通道（webnovel-copilot-300 · M2/T13，流程 F-05）。

三入口：
- 作者手写：直接编辑 `素材/活/*.csv`，author-sync 留账（已有行为，不在此模块）；
- AI 归纳：写章/settle 后候选条目 → **先入画廊** `素材/regen/{slug}-v{N}.csv`；
- 拆书投喂：deconstruction-agent 抽零件 → 画廊同上。
作者 `adopt` 采纳才入活层（来源随行入库：AI归纳 / 拆书:<出处>）；`discard` 删批。
红线：画廊只增不改（adopt 不删批文件）；非法通道（作者手写）不得走画廊。
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .author_journal import append_events
from .material_store import SKELETON_COLUMNS, normalize_table

INTAKE_SCHEMA_VERSION = "material-intake/1"
GALLERY_DIR = Path("素材") / "regen"

# 允许走画廊的来源通道（作者手写直编活层，不经过画廊）
_CHANNEL_PATTERN = re.compile(r"^(AI归纳|拆书:.+|工坊采纳:.+)$")
_CHANNEL_SLUG = {"AI归纳": "ai", "拆书": "chaishu", "工坊采纳": "gongfang"}
_INTAKE_COLUMNS = ("表", *SKELETON_COLUMNS)


def gallery_dir(project_root: str | Path) -> Path:
    return Path(project_root) / GALLERY_DIR


def _channel_slug(channel: str) -> str:
    if channel == "AI归纳":
        return "ai"
    kind = channel.split(":", 1)[0]
    return _CHANNEL_SLUG.get(kind, "misc")


def _read_candidate_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [
            {k: (v or "").strip() for k, v in row.items() if k in _INTAKE_COLUMNS}
            for row in csv.DictReader(file)
            if any((v or "").strip() for v in row.values())
        ]


def propose_entries(project_root: str | Path, *, channel: str, file: str | Path) -> dict[str, Any]:
    """候选条目入画廊（一批一文件，追加编号）。留 journal(regen, domain=素材)。"""
    if not _CHANNEL_PATTERN.match(str(channel or "").strip()):
        return {"ok": False, "error": "invalid_channel", "channel": channel}
    source = Path(file)
    if not source.is_file():
        return {"ok": False, "error": "file_missing", "file": str(source)}
    rows = _read_candidate_rows(source)
    if not rows:
        return {"ok": False, "error": "empty_file", "file": str(source)}
    for row in rows:
        if normalize_table(row.get("表", "")) is None:
            return {"ok": False, "error": "invalid_table", "table": row.get("表", "")}
        if not row.get("id"):
            return {"ok": False, "error": "missing_id", "table": row.get("表", "")}

    root = Path(project_root)
    gallery = gallery_dir(root)
    gallery.mkdir(parents=True, exist_ok=True)
    slug = _channel_slug(channel.strip())
    existing = [int(m.group(1)) for f in gallery.glob(f"{slug}-v*.csv") if (m := re.fullmatch(rf"{slug}-v(\d+)\.csv", f.name))]
    version = max(existing, default=0) + 1
    batch_name = f"{slug}-v{version}.csv"

    for row in rows:
        row["来源"] = channel.strip()
        row["状态"] = "active"
    with (gallery / batch_name).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(_INTAKE_COLUMNS), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    append_events(
        root,
        [
            {
                "actor": "ai",
                "action": "regen",
                "domain": "素材",
                "path": f"{GALLERY_DIR.as_posix()}/{batch_name}",
                "change_kind": "add",
                "diff_stat": {"ins": len(rows), "del": 0},
                "summary": f"素材候选入画廊 {len(rows)} 条（{channel}）",
                "impact": [],
            }
        ],
    )
    return {
        "ok": True,
        "schema_version": INTAKE_SCHEMA_VERSION,
        "batch": batch_name,
        "channel": channel.strip(),
        "rows": len(rows),
    }


def list_candidates(project_root: str | Path) -> list[dict[str, Any]]:
    """画廊批次清单（按批次序）。"""
    gallery = gallery_dir(project_root)
    if not gallery.is_dir():
        return []
    batches: list[dict[str, Any]] = []
    for file in sorted(gallery.glob("*-v*.csv")):
        rows = _read_candidate_rows(file)
        batches.append({"batch": file.name, "channel": rows[0].get("来源", "") if rows else "", "rows": len(rows)})
    return batches


def adopt_entries(project_root: str | Path, *, batch: str, ids: list[str] | None = None) -> dict[str, Any]:
    """采纳批次（全部或 ids 子集）入活层；id 已存在则跳过。画廊文件保留（只增不改）。"""
    from .material_store import append_entries

    path = gallery_dir(project_root) / batch
    if not path.is_file():
        return {"ok": False, "error": "batch_missing", "batch": batch}
    rows = _read_candidate_rows(path)
    if ids is not None:
        wanted = {str(i).strip() for i in ids}
        rows = [row for row in rows if row.get("id") in wanted]

    adopted = 0
    skipped: list[dict[str, str]] = []
    for row in rows:
        table = normalize_table(row.get("表", ""))
        entry = {col: row.get(col, "") for col in SKELETON_COLUMNS}
        report = append_entries(project_root, table, [entry], source=row.get("来源", ""), journal_summary="")
        if report.get("ok"):
            adopted += 1
        else:
            skipped.append({"id": row.get("id", ""), "reason": report.get("error", "unknown")})

    if adopted:
        append_events(
            project_root,
            [
                {
                    "actor": "author",
                    "action": "adopt",
                    "domain": "素材",
                    "path": f"{GALLERY_DIR.as_posix()}/{batch}",
                    "change_kind": "add",
                    "diff_stat": {"ins": adopted, "del": 0},
                    "summary": f"采纳素材候选 {adopted} 条（{batch}）",
                    "impact": [],
                }
            ],
        )
    return {
        "ok": True,
        "schema_version": INTAKE_SCHEMA_VERSION,
        "batch": batch,
        "adopted": adopted,
        "skipped": skipped,
    }


def discard_batch(project_root: str | Path, *, batch: str) -> dict[str, Any]:
    """丢弃批次（删画廊文件）。留 journal(discard, domain=素材)。"""
    path = gallery_dir(project_root) / batch
    if not path.is_file():
        return {"ok": False, "error": "batch_missing", "batch": batch}
    path.unlink()
    append_events(
        project_root,
        [
            {
                "actor": "author",
                "action": "discard",
                "domain": "素材",
                "path": f"{GALLERY_DIR.as_posix()}/{batch}",
                "change_kind": "structure",
                "diff_stat": {"ins": 0, "del": 0},
                "summary": f"丢弃素材候选批（{batch}）",
                "impact": [],
            }
        ],
    )
    return {"ok": True, "schema_version": INTAKE_SCHEMA_VERSION, "batch": batch}


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python -X utf8 material_intake.py {propose|candidates|adopt|discard} [options]

    一般经 `webnovel.py materials propose|candidates|adopt|discard` 调用。
    """
    import argparse

    parser = argparse.ArgumentParser(description="素材入库三通道（T13）")
    parser.add_argument("action", choices=["propose", "candidates", "adopt", "discard"])
    parser.add_argument("--channel", default="", help="AI归纳 | 拆书:<出处> | 工坊采纳:<提案id>")
    parser.add_argument("--file", default="", help="propose：候选 CSV（列：表 + 骨架列）")
    parser.add_argument("--batch", default="", help="adopt/discard：批次文件名")
    parser.add_argument("--ids", default="", help="adopt：逗号分隔条目 id（缺省整批）")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    if args.action == "propose":
        if not args.channel or not args.file:
            parser.error("propose 需要 --channel 与 --file")
        report = propose_entries(root, channel=args.channel, file=args.file)
    elif args.action == "candidates":
        report = {"ok": True, "batches": list_candidates(root)}
    elif args.action == "adopt":
        if not args.batch:
            parser.error("adopt 需要 --batch")
        ids = [i for i in args.ids.split(",") if i.strip()] or None
        report = adopt_entries(root, batch=args.batch, ids=ids)
    else:
        if not args.batch:
            parser.error("discard 需要 --batch")
        report = discard_batch(root, batch=args.batch)

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok", True) else 1
    if args.action == "candidates":
        for item in report["batches"]:
            print(f"{item['batch']}  {item['channel']}  {item['rows']} 条")
        if not report["batches"]:
            print("(画廊为空)")
    else:
        if not report.get("ok"):
            print(f"ERROR {report.get('error')}")
        elif args.action == "propose":
            print(f"OK 入画廊 {report['batch']}（{report['channel']}，{report['rows']} 条）")
        elif args.action == "adopt":
            print(f"OK 采纳 {report['adopted']} 条；跳过 {len(report['skipped'])} 条")
            for item in report["skipped"]:
                print(f"  SKIP {item['id']}（{item['reason']}）")
        else:
            print(f"OK 已丢弃 {report['batch']}")
    return 0 if report.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
