"""卷纲-实际对账（webnovel-copilot-300 · M6/T30，A7，流程卷收尾）。

卷收尾把「卷纲规划」与「实际产出」做三方 diff，报告落盘
`大纲/卷纲/第NN卷-对账报告.md` 并留 journal（domain=卷纲）：

1. **节点覆盖率**：节拍表「升级危机链」各节点的章节范围（第X-Y章/第X章）
   vs 章纲卡与定稿正文的实际覆盖；
2. **伏笔兑现**：埋设章落在本卷范围的承诺账本条目按状态统计
   （已回收=兑现 / 逾期=逾期 / open·推进中=在途）；
3. **战力里程碑**：卷纲提及的境界链名（来自 力量锚点.yaml 境界链）对照
   通胀记录/章纲战力事件在本卷的落点——命中为已对账，否则未对账。

红线：只读正典+追加报告文件；不改卷纲、不改条目、不改锚点。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .author_journal import append_events
from .chapter_outline_batch import parse_chapter_card
from .power_anchor import load_anchor
from .promise_ledger import load_entries

RECONCILE_SCHEMA_VERSION = "volume-reconcile/1"
_VOLUME_DIR = Path("大纲") / "卷纲"
_RANGE_RE = re.compile(r"第\s*(\d{1,4})\s*[-–~至]\s*(\d{1,4})\s*章|第\s*(\d{1,4})\s*章")


def _node_ranges(plan_text: str) -> list[dict[str, Any]]:
    """节拍表危机链表格行 → [{节点, 描述, 章_start, 章_end}]（无章节范围的行跳过）。"""
    nodes: list[dict[str, Any]] = []
    for line in plan_text.splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= {"|", "-", " ", ":"}:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("节点", "") or set(cells[0]) <= {"-", " "}:
            continue
        if not re.fullmatch(r"\d{1,2}", cells[0]):
            continue
        match = _RANGE_RE.search(cells[1])
        if not match:
            continue
        start = int(match.group(1) or match.group(3))
        end = int(match.group(2)) if match.group(2) else start
        nodes.append({"节点": int(cells[0]), "描述": cells[1], "章_start": start, "章_end": end})
    return nodes


def _chapters_on_disk(project_root: Path) -> set[int]:
    chapters: set[int] = set()
    outline_dir = project_root / "大纲" / "章纲"
    if outline_dir.is_dir():
        for path in outline_dir.glob("*.md"):
            if re.fullmatch(r"\d{1,4}", path.stem):
                chapters.add(int(path.stem))
    body_dir = project_root / "定稿" / "正文"
    if body_dir.is_dir():
        for path in body_dir.glob("*.md"):
            match = re.match(r"(\d{1,4})", path.stem)
            if match:
                chapters.add(int(match.group(1)))
    return chapters


def _realms_of_volume(project_root: Path, plan_text: str) -> list[dict[str, Any]]:
    """卷纲提及的境界链名 → 里程碑候选（取含境界名的行，含章提示）。"""
    chain = [str(level.get("名", "")) for level in (load_anchor(project_root).get("境界链") or []) if level.get("名")]
    milestones: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in plan_text.splitlines():
        for realm in chain:
            if realm in line and realm not in seen:
                hint = re.search(r"第\s*(\d{1,4})\s*章", line)
                milestones.append(
                    {
                        "realm": realm,
                        "excerpt": line.strip().lstrip("- ").lstrip("> ")[:60],
                        "chapter_hint": int(hint.group(1)) if hint else None,
                    }
                )
                seen.add(realm)
    return milestones


def reconcile_volume(project_root: str | Path, *, volume: int) -> dict[str, Any]:
    root = Path(project_root)
    volume_dir = root / _VOLUME_DIR
    plan_path = volume_dir / f"第{int(volume):02d}卷.md"
    beats_path = volume_dir / f"第{int(volume):02d}卷-节拍表.md"
    if not plan_path.is_file():
        return {"ok": False, "error": "volume_plan_missing", "volume": int(volume)}
    plan_text = plan_path.read_text(encoding="utf-8")
    beats_text = beats_path.read_text(encoding="utf-8") if beats_path.is_file() else ""

    # 1) 节点覆盖率
    on_disk = _chapters_on_disk(root)
    node_coverage: list[dict[str, Any]] = []
    for node in _node_ranges(beats_text):
        span = set(range(node["章_start"], node["章_end"] + 1))
        covered = bool(span & on_disk)
        node_coverage.append({**node, "covered": covered})
    coverage = round(sum(1 for n in node_coverage if n["covered"]) / len(node_coverage), 2) if node_coverage else 0.0

    # 2) 伏笔兑现（埋设章落在本卷范围；卷范围 = 节点最小/最大章，无节点时用 50 章默认窗）
    if node_coverage:
        vol_start = min(n["章_start"] for n in node_coverage)
        vol_end = max(n["章_end"] for n in node_coverage)
    else:
        vol_start, vol_end = (int(volume) - 1) * 50 + 1, int(volume) * 50
    counts = {"已回收": 0, "逾期": 0, "在途": 0}
    for entry in load_entries(root):
        planted = int(entry.get("埋设章") or 0)
        if vol_start <= planted <= vol_end:
            status = str(entry.get("状态") or "open")
            due = int(entry.get("最晚回收章") or 0)
            if status == "已回收":
                counts["已回收"] += 1
            elif status == "逾期" or (due and due < vol_end):
                # 对账按卷末口径：本卷应收未收（含扫描器尚未标记的）计逾期
                counts["逾期"] += 1
            else:
                counts["在途"] += 1

    # 3) 战力里程碑（通胀记录落点对账）
    anchor = load_anchor(root)
    inflation = anchor.get("通胀记录") or []
    milestones: list[dict[str, Any]] = []
    for milestone in _realms_of_volume(root, plan_text):
        # A7 v1 口径：本卷通胀记录中该境界有落点即视为已对账（章号提示仅入报告，供人工核对偏差）
        verified = any(
            vol_start <= int(record.get("章") or 0) <= vol_end
            and str(milestone["realm"]) in str(record.get("主角锚点") or "")
            for record in inflation
        )
        milestones.append({**milestone, "verified": verified})

    report_lines = [
        f"# 第 {int(volume)} 卷 · 卷纲-实际对账报告",
        "",
        f"> schema: {RECONCILE_SCHEMA_VERSION}｜卷章范围：{vol_start}-{vol_end}",
        "",
        "## 节点覆盖率",
        "",
        f"- 覆盖率：**{coverage:.0%}**（{sum(1 for n in node_coverage if n['covered'])}/{len(node_coverage)} 节点）",
        "",
    ]
    for node in node_coverage:
        mark = "✅" if node["covered"] else "❌"
        report_lines.append(f"- {mark} 节点{node['节点']}（{node['描述']}）")
    report_lines.extend(["", "## 伏笔兑现", "", f"- 已回收 {counts['已回收']}｜逾期 {counts['逾期']}｜在途 {counts['在途']}", ""])
    report_lines.extend(["## 战力里程碑", ""])
    for milestone in milestones:
        mark = "✅ 已对账" if milestone["verified"] else "❌ 未对账"
        hint = f"（卷纲提示 第{milestone['chapter_hint']}章）" if milestone["chapter_hint"] else ""
        report_lines.append(f"- {mark} {milestone['realm']}{hint}：{milestone['excerpt']}")
    report_lines.append("")

    report_path = volume_dir / f"第{int(volume):02d}卷-对账报告.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8", newline="\n")
    append_events(
        root,
        [
            {
                "actor": "system",
                "action": "edit",
                "domain": "卷纲",
                "path": report_path.relative_to(root).as_posix(),
                "change_kind": "add",
                "diff_stat": {"ins": len(report_lines), "del": 0},
                "summary": f"卷纲-实际对账：卷{int(volume)} 节点覆盖 {coverage:.0%}，伏笔 兑现{counts['已回收']}/逾期{counts['逾期']}，里程碑对账 {sum(1 for m in milestones if m['verified'])}/{len(milestones)}",
                "impact": [],
            }
        ],
    )
    return {
        "ok": True,
        "schema_version": RECONCILE_SCHEMA_VERSION,
        "volume": int(volume),
        "volume_range": [vol_start, vol_end],
        "node_coverage": node_coverage,
        "coverage": coverage,
        "fulfillment": counts,
        "milestones": milestones,
        "report_path": str(report_path),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python -X utf8 volume_reconcile.py --volume N [--format json]

    一般经 `webnovel.py volume-reconcile --volume N` 调用（卷收尾 A7）。
    """
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="卷纲-实际对账（T30/A7）")
    parser.add_argument("--volume", type=int, required=True, help="卷号")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    report = reconcile_volume(Path(args.project_root), volume=args.volume)
    if args.format == "json":
        print(_json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok", True) else 1

    if not report.get("ok"):
        print(f"ERROR {report.get('error')}")
        return 1
    print(f"OK 卷{report['volume']} 对账：节点覆盖 {report['coverage']:.0%}；伏笔 {report['fulfillment']}；里程碑 {sum(1 for m in report['milestones'] if m['verified'])}/{len(report['milestones'])} 已对账")
    print(f"报告：{report['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
