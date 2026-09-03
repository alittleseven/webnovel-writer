"""作者域 journal 数据面（webnovel-copilot-300 · M0/T2）。

- `作者/journal.jsonl`：一行一事、append-only 的事件流（schema 见
  docs/zcode/webnovel-copilot-300/06-data-design.md §3）。
- `作者/.watermark`：author-sync 已处理到的事件序号（1-based）。
- `.webnovel/stale.json`：影响标记（可重建；丢失即视为无 stale）。

写入方：author-sync（脚本分类）、语义补全、freeze/retcon/采纳等系统动作。
红线：只追加不修改历史行；残行（崩溃中写入）读取时忽略。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

JOURNAL_SCHEMA_VERSION = "journal/1"
JOURNAL_REL = Path("作者") / "journal.jsonl"
WATERMARK_REL = Path("作者") / ".watermark"
STALE_REL = Path(".webnovel") / "stale.json"

VALID_ACTORS = ("author", "system", "ai")
VALID_ACTIONS = ("edit", "adopt", "freeze", "retcon", "settle", "regen", "discard", "learn", "enrich")
VALID_DOMAINS = ("总纲", "卷纲", "章纲", "条目", "素材", "设定", "战力", "正文", "文风", "其他")
VALID_CHANGE_KINDS = ("content", "style", "fact", "structure", "add", "delete")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def journal_path(project_root: str | Path) -> Path:
    return Path(project_root) / JOURNAL_REL


def append_events(project_root: str | Path, events: list[dict[str, Any]]) -> int:
    """按序追加事件（一行一事，内部换行转义保证行完整性）。返回追加条数。"""
    path = journal_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for event in events:
        payload = dict(event)
        payload.setdefault("ts", _utc_now_iso())
        summary = str(payload.get("summary") or "")
        if "\n" in summary:
            payload["summary"] = summary.replace("\r\n", "\n").replace("\n", "⏎")
        lines.append(json.dumps(payload, ensure_ascii=False))
    with path.open("a", encoding="utf-8", newline="\n") as file:
        for line in lines:
            file.write(line + "\n")
    return len(lines)


def read_journal(project_root: str | Path, *, after_index: int = 0) -> list[dict[str, Any]]:
    """读取事件流（1-based；after_index=N 返回第 N 条之后的事件）。

    末尾残行（非法 JSON）忽略——append-only 流的崩溃安全读取语义。
    """
    path = journal_path(project_root)
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events[after_index:] if after_index > 0 else events


def read_watermark(project_root: str | Path) -> int:
    path = Path(project_root) / WATERMARK_REL
    if not path.is_file():
        return 0
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0")
    except ValueError:
        return 0


def write_watermark(project_root: str | Path, index: int) -> None:
    path = Path(project_root) / WATERMARK_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{int(index)}\n", encoding="utf-8", newline="\n")


def pending_semantic(project_root: str | Path, *, batch_limit: int = 50) -> list[dict[str, Any]]:
    """待语义补全事件（summary 为空的 edit 事件，D0-3：每会话一次 ≤50 条）。"""
    pending: list[dict[str, Any]] = []
    for index, event in enumerate(read_journal(project_root), start=1):
        if len(pending) >= batch_limit:
            break
        if event.get("action") == "edit" and not str(event.get("summary") or "").strip():
            pending.append(
                {
                    "index": index,
                    "domain": event.get("domain"),
                    "path": event.get("path"),
                    "diff_stat": event.get("diff_stat"),
                }
            )
    return pending


def append_enrichment(
    project_root: str | Path,
    *,
    ref_index: int,
    summary: str,
    change_kind: str | None = None,
) -> int:
    """为第 ref_index 条事件追加语义补全（action=enrich，actor=ai）。

    红线：不改历史行；读取层（read_journal_view）把 enrich 合成进被引用事件。
    """
    event: dict[str, Any] = {
        "actor": "ai",
        "action": "enrich",
        "domain": "其他",
        "path": f"(enrich:{ref_index})",
        "change_kind": change_kind or "content",
        "diff_stat": {"ins": 0, "del": 0},
        "summary": summary,
        "impact": [],
        "ref_index": int(ref_index),
    }
    return append_events(project_root, [event])


def read_journal_view(project_root: str | Path) -> list[dict[str, Any]]:
    """合成视图：enrich 事件的 summary/change_kind 应用到被引用的 edit 事件。"""
    events = read_journal(project_root)
    enrich_by_ref: dict[int, dict[str, Any]] = {}
    for event in events:
        ref = event.get("ref_index")
        if event.get("action") == "enrich" and isinstance(ref, int):
            enrich_by_ref[ref] = event
    view: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        if event.get("action") == "enrich":
            continue  # 补全事件不单独出现在视图
        merged = dict(event)
        enrich = enrich_by_ref.get(index)
        if enrich is not None:
            merged["summary"] = enrich.get("summary") or merged.get("summary")
            if enrich.get("change_kind"):
                merged["change_kind"] = enrich.get("change_kind")
            merged["enriched"] = True
        view.append(merged)
    return view


def validate_journal(project_root: str | Path) -> list[str]:
    """校验事件字段合法域（actor/action/domain/change_kind）。返回问题描述列表。"""
    problems: list[str] = []
    for index, event in enumerate(read_journal(project_root), start=1):
        if event.get("actor") not in VALID_ACTORS:
            problems.append(f"event#{index}: actor 非法（{event.get('actor')}）")
        if event.get("action") not in VALID_ACTIONS:
            problems.append(f"event#{index}: action 非法（{event.get('action')}）")
        if event.get("domain") not in VALID_DOMAINS:
            problems.append(f"event#{index}: domain 非法（{event.get('domain')}）")
        if event.get("change_kind") not in VALID_CHANGE_KINDS:
            problems.append(f"event#{index}: change_kind 非法（{event.get('change_kind')}）")
    return problems


# ---------------------------------------------------------------------------
# stale 标记（可重建）
# ---------------------------------------------------------------------------

def _stale_path(project_root: str | Path) -> Path:
    return Path(project_root) / STALE_REL


def read_stale(project_root: str | Path) -> list[dict[str, Any]]:
    path = _stale_path(project_root)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    items = payload.get("items")
    return list(items) if isinstance(items, list) else []


def _write_stale(project_root: str | Path, items: list[dict[str, Any]]) -> None:
    path = _stale_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "stale/1",
        "generated_at": _utc_now_iso(),
        "items": items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def mark_stale(project_root: str | Path, *, target: str, reason: str, impact: list[str] | None = None) -> None:
    """标记 stale（同 target 覆盖合并，reason 取最新）。"""
    items = [dict(item) for item in read_stale(project_root)]
    entry = {
        "target": target,
        "reason": reason,
        "impact": list(impact or []),
        "since": _utc_now_iso(),
        "consumed": False,
    }
    items = [item for item in items if item.get("target") != target]
    items.append(entry)
    _write_stale(project_root, items)


def consume_stale(project_root: str | Path, target: str) -> None:
    items = [dict(item) for item in read_stale(project_root)]
    changed = False
    for item in items:
        if item.get("target") == target and not item.get("consumed"):
            item["consumed"] = True
            changed = True
    if changed:
        _write_stale(project_root, items)


def unconsumed_stale(project_root: str | Path) -> list[dict[str, Any]]:
    return [item for item in read_stale(project_root) if not item.get("consumed")]


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python -X utf8 author_journal.py stats|validate [--project-root P]"""
    import argparse

    parser = argparse.ArgumentParser(description="作者域 journal 数据面（T2）")
    parser.add_argument("action", choices=["stats", "validate"])
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    if args.action == "validate":
        problems = validate_journal(root)
        if args.format == "json":
            print(json.dumps({"ok": not problems, "problems": problems}, ensure_ascii=False, indent=2))
        else:
            print("OK journal" if not problems else "ERROR journal")
            for problem in problems:
                print(f"- {problem}")
        return 0 if not problems else 1

    events = read_journal(root)
    by_domain: dict[str, int] = {}
    by_action: dict[str, int] = {}
    for event in events:
        by_domain[str(event.get("domain"))] = by_domain.get(str(event.get("domain")), 0) + 1
        by_action[str(event.get("action"))] = by_action.get(str(event.get("action")), 0) + 1
    payload = {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "total": len(events),
        "watermark": read_watermark(root),
        "by_domain": by_domain,
        "by_action": by_action,
        "unconsumed_stale": len(unconsumed_stale(root)),
    }
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"journal events: {payload['total']} (watermark={payload['watermark']}, stale={payload['unconsumed_stale']})")
        for domain, count in sorted(by_domain.items(), key=lambda kv: -kv[1]):
            print(f"  {domain}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
