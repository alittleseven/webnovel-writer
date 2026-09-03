"""治理视图数据层（webnovel-copilot-300 · M7/T32，F-14）。

为 dashboard 提供六组只读治理视图的数据快照（纯文件读取，缺文件优雅降级）：
1. outline_zones 总纲三区状态（甲区冻结/乙区活跃/丙区锚点的小节数与行数）；
2. freeze 冻结进度（定版 v{NN} manifest 清单 + 演化 freeze/retcon 事件）；
3. journal 时间线（作者域事件流最近 50 条，新→旧）；
4. materials 素材热力（十表条数 + 使用轨迹 top 条目）；
5. inflation 通胀曲线（力量锚点通胀记录 + 战例账本计数）；
6. alerts 红点（stale 未消费 / 伏笔逾期 / 画廊积压）。

红线：只读；任何子视图失败返回空结构，不影响整体快照。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

GOVERNANCE_SCHEMA_VERSION = "governance-snapshot/1"
JOURNAL_TIMELINE_LIMIT = 50
ZONE_NAMES = ("甲区", "乙区", "丙区")


def _outline_zones(root: Path) -> dict[str, Any]:
    outline = root / "大纲" / "总纲.md"
    zones: dict[str, dict[str, Any]] = {}
    current: str | None = None
    if outline.is_file():
        for line in outline.read_text(encoding="utf-8").splitlines():
            heading = re.match(r"^#{1,4}\s*(.*)", line)
            if heading:
                text = heading.group(1)
                for zone in ZONE_NAMES:
                    if zone in text:
                        current = zone
            if current:
                zones.setdefault(current, {"标题数": 0, "行数": 0})
                if heading:
                    zones[current]["标题数"] += 1
                elif line.strip():
                    zones[current]["行数"] += 1
    return {"zones": zones, "has_master": outline.is_file()}


def _freeze_progress(root: Path) -> dict[str, Any]:
    versions: list[dict[str, Any]] = []
    definitive = root / "素材" / "定版"
    if definitive.is_dir():
        for path in sorted(definitive.glob("v*/manifest.json")):
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            versions.append(
                {
                    "version": path.parent.name,
                    "volume": manifest.get("volume"),
                    "frozen_at": manifest.get("frozen_at"),
                    "files": len(manifest.get("source_files") or []),
                }
            )
    events = 0
    evolution = root / "演化"
    if evolution.is_dir():
        events = len(list(evolution.glob("freeze-v*.json"))) + len(list(evolution.glob("retcon-v*.json")))
    return {"versions": versions, "events": events}


def _journal_timeline(root: Path, limit: int = JOURNAL_TIMELINE_LIMIT) -> list[dict[str, Any]]:
    try:
        from data_modules.author_journal import read_journal_view

        events = read_journal_view(root)[-limit:]
    except Exception:
        return []
    return [
        {
            "ts": str(event.get("ts") or ""),
            "actor": str(event.get("actor") or ""),
            "action": str(event.get("action") or ""),
            "domain": str(event.get("domain") or ""),
            "summary": str(event.get("summary") or ""),
        }
        for event in reversed(events)
    ]


def _materials_heat(root: Path) -> dict[str, Any]:
    try:
        from data_modules.material_store import MATERIAL_TABLES, read_table

        tables = {
            table: {"total": len(rows), "active": sum(1 for r in rows if r.get("状态") == "active")}
            for table in MATERIAL_TABLES
            for rows in [read_table(root, table, include_archived=True)]
        }
    except Exception:
        tables = {}
    heat: list[dict[str, Any]] = []
    trajectory = root / "素材" / "使用轨迹.jsonl"
    if trajectory.is_file():
        counts: dict[str, int] = {}
        for line in trajectory.read_text(encoding="utf-8").splitlines():
            try:
                entry_id = json.loads(line).get("条目id")
            except json.JSONDecodeError:
                continue
            if entry_id:
                counts[entry_id] = counts.get(entry_id, 0) + 1
        heat = [
            {"id": entry_id, "uses": uses}
            for entry_id, uses in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
        ]
    return {"tables": tables, "top_used": heat}


def _inflation_curve(root: Path) -> dict[str, Any]:
    anchor = root / "设定" / "力量锚点.yaml"
    records: list[dict[str, Any]] = []
    battles = 0
    if anchor.is_file():
        try:
            from data_modules.power_anchor import load_anchor

            data = load_anchor(root)
            records = sorted(
                (
                    {
                        "章": int(r.get("章") or 0),
                        "主角锚点": str(r.get("主角锚点") or ""),
                        "事件": str(r.get("事件") or ""),
                        "偏差": str(r.get("偏差") or ""),
                    }
                    for r in (data.get("通胀记录") or [])
                ),
                key=lambda r: r["章"],
            )
            battles = len(data.get("战例账本") or [])
        except Exception:
            records = []
    return {"records": records, "battles": battles}


def _alerts(root: Path) -> dict[str, Any]:
    stale: list[dict[str, Any]] = []
    try:
        from data_modules.author_journal import unconsumed_stale

        stale = [
            {"target": s.get("target"), "reason": s.get("reason")}
            for s in unconsumed_stale(root)[:20]
        ]
    except Exception:
        stale = []

    overdue: list[dict[str, Any]] = []
    try:
        from data_modules.promise_ledger import foreshadow_scan

        latest = _latest_chapter_hint(root)
        overdue = [
            {"编号": e["编号"], "名称": e["名称"], "最晚回收章": e["最晚回收章"]}
            for e in foreshadow_scan(root, current_chapter=latest, apply=False)["overdue"]
        ]
    except Exception:
        overdue = []

    gallery = 0
    for rel in ("素材/regen", "大纲/regen"):
        directory = root / rel
        if directory.is_dir():
            gallery += sum(1 for _ in directory.rglob("*") if _.is_file())

    return {"stale": stale, "overdue": overdue, "gallery_files": gallery}


def _latest_chapter_hint(root: Path) -> int:
    body_dir = root / "定稿" / "正文"
    latest = 1
    if body_dir.is_dir():
        for path in body_dir.glob("*.md"):
            match = re.match(r"(\d{1,4})", path.stem)
            if match:
                latest = max(latest, int(match.group(1)))
    return latest


def build_governance_snapshot(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    return {
        "schema_version": GOVERNANCE_SCHEMA_VERSION,
        "outline_zones": _outline_zones(root),
        "freeze": _freeze_progress(root),
        "journal": _journal_timeline(root),
        "materials": _materials_heat(root),
        "inflation": _inflation_curve(root),
        "alerts": _alerts(root),
    }
