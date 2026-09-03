"""承诺账本与逾期扫描（webnovel-copilot-300 · M6/T28，A3/F-13）。

`大纲/条目/{伏笔,悬念,感情线}/{编号}-{名称}.md` 是统一承诺账本（取代 v6
override_ledger 与 v7 决策卡豁免的分裂），front matter：
`编号/类型/名称/状态/埋设章/最晚回收章/回收章`，正文自由补充。

- 状态机（06 §12-4）：open → 推进中 → 已回收 | 作废；`逾期` 由扫描器从
  open/推进中 自动标记（06 §1：条目状态挂最晚回收章 → 逾期扫描器）。
- `foreshadow_scan`：承诺账本 × 最晚回收章 × 当前章号，逾期全数报出并标记
  （存在 逾期 时 CLI 非零退出，供卷收尾/doctor 门禁消费）。
- `pending_for_chapter`：write 链「本章应推进项」= 逾期 + 10 章窗内即将到期
  + 本章章纲卡承诺推进引用。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .author_journal import append_events

LEDGER_SCHEMA_VERSION = "promise-ledger/1"
ENTRY_ROOT = Path("大纲") / "条目"
KINDS: dict[str, str] = {"伏笔": "F", "悬念": "S", "感情线": "R"}
STATUS_VALUES = ("open", "推进中", "已回收", "作废", "逾期")
LEGAL_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "open": ("推进中", "已回收", "作废", "逾期"),
    "推进中": ("已回收", "作废", "逾期"),
    "逾期": ("推进中", "已回收", "作废"),
    "已回收": (),
    "作废": (),
}
DUE_SOON_WINDOW = 10
_FRONT_FIELDS = ("编号", "类型", "名称", "状态", "埋设章", "最晚回收章", "回收章")
_INT_FIELDS = {"埋设章", "最晚回收章", "回收章"}


def ledger_dir(project_root: str | Path, kind: str | None = None) -> Path:
    base = Path(project_root) / ENTRY_ROOT
    return base / kind if kind else base


def _entry_path(project_root: Path, entry: dict[str, Any]) -> Path:
    slug = re.sub(r"[\\\\/:*?\"<>|\s]+", "", str(entry.get("名称", "")))[:20]
    return ledger_dir(project_root, str(entry["类型"])) / f"{entry['编号']}-{slug}.md"


def _parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fields: dict[str, Any] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key in _INT_FIELDS:
            fields[key] = int(value) if value.strip() else 0
        elif key:
            fields[key] = value
    return fields, parts[2].lstrip("\n")


def parse_entry(path: Path) -> dict[str, Any]:
    fields, body = _parse_front_matter(Path(path).read_text(encoding="utf-8"))
    return {**{k: fields.get(k, 0 if k in _INT_FIELDS else "") for k in _FRONT_FIELDS}, "正文": body.strip(), "path": str(path)}


def load_entries(project_root: str | Path, *, kind: str | None = None) -> list[dict[str, Any]]:
    kinds = [kind] if kind else list(KINDS)
    entries: list[dict[str, Any]] = []
    for k in kinds:
        directory = ledger_dir(project_root, k)
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            entries.append(parse_entry(path))
    return sorted(entries, key=lambda e: e["编号"])


def create_entry(
    project_root: str | Path,
    *,
    kind: str,
    name: str,
    planted_chapter: int,
    due_chapter: int,
    note: str = "",
    entry_id: str | None = None,
) -> dict[str, Any]:
    """登记一条承诺（编号按类型前缀自动递增）。留 journal(add, 条目)。"""
    if kind not in KINDS:
        return {"ok": False, "error": "invalid_kind", "allowed": list(KINDS)}
    name = str(name or "").strip()
    if not name:
        return {"ok": False, "error": "missing_name"}
    root = Path(project_root)
    prefix = KINDS[kind]
    existing = [e["编号"] for e in load_entries(root, kind=kind)]
    seq = max((int(e.split("-")[1]) for e in existing if "-" in e), default=0) + 1
    entry_id = entry_id or f"{prefix}-{seq:03d}"

    entry = {
        "编号": entry_id,
        "类型": kind,
        "名称": name,
        "状态": "open",
        "埋设章": int(planted_chapter),
        "最晚回收章": int(due_chapter),
        "回收章": 0,
    }
    path = _entry_path(root, entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}: {entry[k]}" for k in _FRONT_FIELDS]
    text = "---\n" + "\n".join(lines) + "\n---\n" + (f"\n{note}\n" if note else "\n")
    path.write_text(text, encoding="utf-8", newline="\n")
    append_events(
        root,
        [
            {
                "actor": "author",
                "action": "add",
                "domain": "条目",
                "path": path.relative_to(root).as_posix(),
                "change_kind": "add",
                "diff_stat": {"ins": 1, "del": 0},
                "summary": f"登记承诺 {entry_id}「{name}」（最晚回收章 {due_chapter}）",
                "impact": [],
            }
        ],
    )
    return {"ok": True, "schema_version": LEDGER_SCHEMA_VERSION, "id": entry_id, "path": str(path)}


def update_status(project_root: str | Path, *, entry_id: str, status: str, chapter: int | None = None) -> dict[str, Any]:
    """状态机流转（非法迁移拒绝）；已回收必须带回收章。留 journal(edit, 条目)。"""
    if status not in STATUS_VALUES:
        return {"ok": False, "error": "invalid_status", "status": status}
    root = Path(project_root)
    entries = {e["编号"]: e for e in load_entries(root)}
    entry = entries.get(entry_id)
    if entry is None:
        return {"ok": False, "error": "not_found", "id": entry_id}
    if status == entry["状态"]:
        return {"ok": True, "id": entry_id, "status": status, "unchanged": True}
    if status not in LEGAL_TRANSITIONS.get(entry["状态"], ()):
        return {"ok": False, "error": "illegal_transition", "from": entry["状态"], "to": status}

    entry["状态"] = status
    if status == "已回收":
        if chapter is None:
            chapter = int(entry["埋设章"])
        entry["回收章"] = int(chapter)
    path = _entry_path(root, entry)
    body = entry.get("正文", "")
    lines = [f"{k}: {entry[k]}" for k in _FRONT_FIELDS]
    path.write_text("---\n" + "\n".join(lines) + "\n---\n" + (f"\n{body}\n" if body else "\n"), encoding="utf-8", newline="\n")
    append_events(
        root,
        [
            {
                "actor": "author",
                "action": "edit",
                "domain": "条目",
                "path": path.relative_to(root).as_posix(),
                "change_kind": "structure",
                "diff_stat": {"ins": 0, "del": 0},
                "summary": f"{entry_id} 状态 → {status}" + (f"（回收章 {chapter}）" if status == "已回收" else ""),
                "impact": [],
            }
        ],
    )
    return {"ok": True, "id": entry_id, "status": status}


def foreshadow_scan(project_root: str | Path, *, current_chapter: int, apply: bool = True) -> dict[str, Any]:
    """逾期扫描：状态 ∈ {open, 推进中} 且 最晚回收章 < 当前章 → 全数报出并标逾期。"""
    root = Path(project_root)
    current = int(current_chapter)
    overdue: list[dict[str, Any]] = []
    due_soon: list[dict[str, Any]] = []
    for entry in load_entries(root):
        if entry["状态"] not in ("open", "推进中", "逾期"):
            continue
        due = int(entry["最晚回收章"] or 0)
        if due and due < current:
            overdue.append(entry)
            if apply and entry["状态"] != "逾期":
                update_status(root, entry_id=entry["编号"], status="逾期")
                entry["状态"] = "逾期"
        elif due and due <= current + DUE_SOON_WINDOW:
            due_soon.append(entry)
    return {
        "ok": not overdue,
        "schema_version": LEDGER_SCHEMA_VERSION,
        "current_chapter": current,
        "overdue": overdue,
        "due_soon": due_soon,
    }


def pending_for_chapter(project_root: str | Path, *, chapter: int) -> dict[str, Any]:
    """write 链「本章应推进项」：逾期 + 即将到期 + 章纲卡承诺推进引用。"""
    root = Path(project_root)
    scan = foreshadow_scan(root, current_chapter=chapter, apply=False)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in scan["overdue"] + scan["due_soon"]:
        items.append({"编号": entry["编号"], "名称": entry["名称"], "状态": entry["状态"], "最晚回收章": entry["最晚回收章"], "来源": "账本"})
        seen.add(entry["编号"])

    from .chapter_outline_batch import parse_chapter_card

    card_path = root / "大纲" / "章纲" / f"{int(chapter):04d}.md"
    from_card: list[str] = []
    if card_path.is_file():
        fields, _ = parse_chapter_card(card_path.read_text(encoding="utf-8"))
        refs = fields.get("承诺推进") or []
        if isinstance(refs, str):
            refs = [refs]
        for ref in refs:
            from_card.append(str(ref))
            ref_id = str(ref).split(":")[0].strip()
            if ref_id in KINDS.values() or re.match(r"^[FSR]-\d+", ref_id):
                if ref_id not in seen:
                    entry = next((e for e in load_entries(root) if e["编号"] == ref_id), None)
                    if entry:
                        items.append({"编号": entry["编号"], "名称": entry["名称"], "状态": entry["状态"], "最晚回收章": entry["最晚回收章"], "来源": "章纲卡"})
                        seen.add(ref_id)
    return {
        "ok": True,
        "schema_version": LEDGER_SCHEMA_VERSION,
        "chapter": int(chapter),
        "items": items,
        "from_card": from_card,
    }


def crud_main(argv: list[str] | None = None) -> int:
    """CRUD CLI 入口：python -X utf8 promise_ledger.py CRUD {create|list|update}

    一般经 `webnovel.py promise-ledger create|list|update` 调用。
    """
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="承诺账本 CRUD（T28）")
    parser.add_argument("action", choices=["create", "list", "update"])
    parser.add_argument("--kind", default="", help="create/list：伏笔|悬念|感情线")
    parser.add_argument("--name", default="")
    parser.add_argument("--planted-chapter", type=int, default=0)
    parser.add_argument("--due-chapter", type=int, default=0)
    parser.add_argument("--note", default="")
    parser.add_argument("--id", default="")
    parser.add_argument("--status", default="")
    parser.add_argument("--chapter", type=int, default=None)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    if args.action == "create":
        if not args.kind or not args.name or not args.due_chapter:
            parser.error("create 需要 --kind --name --due-chapter")
        report = create_entry(
            root, kind=args.kind, name=args.name,
            planted_chapter=args.planted_chapter, due_chapter=args.due_chapter, note=args.note,
        )
    elif args.action == "list":
        report = {"ok": True, "entries": load_entries(root, kind=args.kind or None)}
    else:
        if not args.id or not args.status:
            parser.error("update 需要 --id 与 --status")
        report = update_status(root, entry_id=args.id, status=args.status, chapter=args.chapter)

    if args.format == "json":
        print(_json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok", True) else 1

    if args.action == "create":
        print(f"OK 已登记 {report.get('id')}" if report.get("ok") else f"ERROR {report.get('error')}")
    elif args.action == "list":
        for entry in report["entries"]:
            print(f"{entry['编号']}「{entry['名称']}」[{entry['状态']}] 埋设{entry['埋设章']} 最晚{entry['最晚回收章']}")
        if not report["entries"]:
            print("（账本为空）")
    else:
        print(f"OK {report.get('id')} → {report.get('status')}" + ("（无变化）" if report.get("unchanged") else "") if report.get("ok") else f"ERROR {report.get('error')} {report.get('from', '')}")
    return 0 if report.get("ok", True) else 1


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python -X utf8 promise_ledger.py {scan|pending} [options]

    一般经 `webnovel.py foreshadow-scan scan|pending` 调用。
    """
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="承诺账本与逾期扫描（T28/A3）")
    parser.add_argument("action", choices=["scan", "pending"])
    parser.add_argument("--chapter", type=int, required=True, help="当前章号（扫描基准）")
    parser.add_argument("--no-apply", dest="apply", action="store_false", help="scan 只报告不标记逾期")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    if args.action == "scan":
        report = foreshadow_scan(root, current_chapter=args.chapter, apply=args.apply)
    else:
        report = pending_for_chapter(root, chapter=args.chapter)

    if args.format == "json":
        print(_json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok", True) else 1

    if args.action == "scan":
        if report["overdue"]:
            print(f"逾期 {len(report['overdue'])} 条：")
            for entry in report["overdue"]:
                print(f"  {entry['编号']}「{entry['名称']}」最晚回收章 {entry['最晚回收章']} < 当前 {args.chapter}")
        else:
            print("OK 无逾期承诺")
        for entry in report["due_soon"]:
            print(f"  即将到期 {entry['编号']}「{entry['名称']}」（{DUE_SOON_WINDOW} 章窗内，最晚 {entry['最晚回收章']}）")
    else:
        print(f"第 {args.chapter} 章应推进项：")
        for item in report["items"]:
            print(f"  {item['编号']}「{item['名称']}」[{item['状态']}] 最晚 {item['最晚回收章']}（{item['来源']}）")
        if not report["items"]:
            print("  （无）")
    return 0 if report.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
