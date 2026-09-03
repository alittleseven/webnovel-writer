"""力量锚点数据面（webnovel-copilot-300 · M4/T18-T19，06 §8 / F-09）。

`设定/力量锚点.yaml` 是双层战力模型的硬校验层：
- `境界链`：序/名/差距描述/寿元——从 力量体系.md **半自动抽取**（extract_candidates
  0 token 出候选，作者 `--apply` 确认才落盘；既有锚点表一律不覆盖，作者主权 P1/P2）；
- `越级规则`：06 §8 默认文案（跨1阶任一依据 / 跨2阶金手指+代价双列且卷纲预告）；
- `战例账本`：data-agent 从正文提取（T19 `record_battle` 登记，作者可改）；
- `通胀记录`：settle 时追加（T19），对账卷纲里程碑。

YAML 为本模块自定义的最小读写器（固定 schema、人类可编辑）。
红线：抽取/校验只读；落盘只在作者确认后发生。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .author_journal import append_events

ANCHOR_SCHEMA_VERSION = "power-anchor/1"
ANCHOR_REL = Path("设定") / "力量锚点.yaml"
_POWER_SOURCES = ("定稿/设定/力量体系.md", "设定集/力量体系.md")
LIST_KEYS = ("境界链", "战例账本", "通胀记录")
DEFAULT_CROSS_RULES = {
    "跨1阶": "需列依据（金手指/代价/外因 任一）",
    "跨2阶": "必须金手指+代价双列，且卷纲有预告",
}
# T19 软校验阈值：通胀偏差连续超阈值章数
INFLATION_THRESHOLD_CHAPTERS = 3


def anchor_path(project_root: str | Path) -> Path:
    return Path(project_root) / ANCHOR_REL


def load_anchor(project_root: str | Path) -> dict[str, Any]:
    """读锚点表（缺失时返回 06 §8 默认骨架；残缺字段回填默认值）。"""
    path = anchor_path(project_root)
    anchor: dict[str, Any] = {
        "spec": ANCHOR_SCHEMA_VERSION,
        "境界链": [],
        "越级规则": dict(DEFAULT_CROSS_RULES),
        "战例账本": [],
        "通胀记录": [],
    }
    if not path.is_file():
        return anchor
    parsed = _parse_anchor(path.read_text(encoding="utf-8"))
    for key, value in parsed.items():
        if key == "越级规则" and isinstance(value, dict):
            merged = dict(DEFAULT_CROSS_RULES)
            merged.update(value)
            anchor[key] = merged
        elif key in LIST_KEYS and isinstance(value, list):
            anchor[key] = value
        elif key == "spec":
            anchor[key] = value
    return anchor


def write_anchor(project_root: str | Path, anchor: dict[str, Any]) -> Path:
    """发射固定 schema 的锚点 YAML（确定性；apply 之外的原始写入入口）。"""
    path = anchor_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [f"spec: {anchor.get('spec', ANCHOR_SCHEMA_VERSION)}"]

    def _emit_item(item: dict[str, Any]) -> list[str]:
        out: list[str] = []
        for key, value in item.items():
            if isinstance(value, dict):
                out.append(f"    {key}:")
                for sub_key, sub_value in value.items():
                    out.append(f"      {sub_key}: {_emit(sub_value)}")
            else:
                out.append(f"    {key}: {_emit(value)}")
        return out

    for list_key in LIST_KEYS:
        lines.append(f"{list_key}:")
        for item in anchor.get(list_key) or []:
            lines.append(f"  - {_first_field(item, list_key)}")
            lines.extend(_rest_fields(item, list_key))
    rules = anchor.get("越级规则") or {}
    lines.append("越级规则:")
    for key, value in rules.items():
        lines.append(f"  {key}: {_emit(value)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _first_field(item: dict[str, Any], list_key: str) -> str:
    if list_key == "境界链":
        return f"序: {_emit(item.get('序'))}"
    if list_key == "战例账本":
        return f"章: {_emit(item.get('章'))}"
    return f"章: {_emit(item.get('章'))}"


def _rest_fields(item: dict[str, Any], list_key: str) -> list[str]:
    first = {"境界链": "序", "战例账本": "章", "通胀记录": "章"}[list_key]
    out: list[str] = []
    for key, value in item.items():
        if key == first:
            continue
        if isinstance(value, dict):
            out.append(f"    {key}:")
            for sub_key, sub_value in value.items():
                out.append(f"      {sub_key}: {_emit(sub_value)}")
        else:
            out.append(f"    {key}: {_emit(value)}")
    return out


def _emit(value: Any) -> str:
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return str(value)


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _parse_anchor(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    section: str | None = None
    current_item: dict[str, Any] | None = None
    nested_key: str | None = None
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0:
            key, _, value = line.partition(":")
            key = key.strip()
            if value.strip() == "":
                section = key
                result[key] = [] if key in LIST_KEYS else {}
                current_item = None
            else:
                section = None
                result[key] = _parse_scalar(value)
        elif line.startswith("- ") and section in LIST_KEYS:
            current_item = {}
            nested_key = None
            key, _, value = line[2:].partition(":")
            key, value = key.strip(), value.strip()
            if value == "":
                nested_key = key
                current_item[key] = {}
            else:
                current_item[key] = _parse_scalar(value)
            result[section].append(current_item)
        elif section in LIST_KEYS and current_item is not None:
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip()
            if indent <= 4:
                if value == "":
                    nested_key = key
                    current_item[key] = {}
                else:
                    nested_key = None
                    current_item[key] = _parse_scalar(value)
            elif nested_key is not None:
                current_item[nested_key][key] = _parse_scalar(value)
        elif section == "越级规则":
            key, _, value = line.partition(":")
            result[section][key.strip()] = _parse_scalar(value)
    return result


# ---------------------------------------------------------------------------
# 半自动抽取（05 §3：作者确认后才落盘）
# ---------------------------------------------------------------------------

def _power_source(project_root: Path) -> Path | None:
    for rel in _POWER_SOURCES:
        candidate = project_root / rel
        if candidate.is_file():
            return candidate
    matches = [p for p in project_root.glob("**/力量体系.md") if ".git" not in p.parts]
    return matches[0] if matches else None


def extract_candidates(project_root: str | Path) -> dict[str, Any]:
    """从 力量体系.md 抽锚点候选（0 token，只读）：等级顺序行定序，能力行补差距描述/寿元。"""
    root = Path(project_root)
    source = _power_source(root)
    if source is None:
        return {"ok": False, "error": "source_missing"}
    text = source.read_text(encoding="utf-8")

    chain_line: str | None = None
    for line in text.splitlines():
        stripped = line.strip().lstrip("-").strip()
        if stripped.startswith("等级顺序") and ("→" in stripped or "->" in stripped):
            chain_line = stripped
            break
    if chain_line is None:
        for line in text.splitlines():
            stripped = line.strip().lstrip("-").strip()
            if "境界链" in stripped and "：" in stripped and "→" in stripped:
                chain_line = stripped
                break
    if chain_line is None:
        return {"ok": False, "error": "chain_line_missing", "source": str(source)}

    raw_chain = chain_line.partition("：")[2] if "：" in chain_line else chain_line.partition(":")[2]
    candidates: list[dict[str, str]] = []
    for index, part in enumerate(raw_chain.split("→"), start=1):
        part = part.strip()
        if not part:
            continue
        name = part.split("(")[0].split("（")[0].strip()
        if name:
            candidates.append({"序": index, "名": name, "差距描述": "", "寿元": ""})

    names = {c["名"] for c in candidates}
    for line in text.splitlines():
        stripped = line.strip().lstrip("-").strip()
        match = re.match(r"([\u4e00-\u9fa5A-Za-z0-9]+)：(.+)", stripped)
        if not match:
            continue
        name, description = match.group(1), match.group(2).strip()
        if name not in names:
            continue
        for candidate in candidates:
            if candidate["名"] == name and not candidate["差距描述"]:
                candidate["差距描述"] = description
                life = re.search(r"寿命(\d+)", description)
                candidate["寿元"] = life.group(1) if life else ""

    return {"ok": True, "source": str(source), "candidates": candidates}


def apply_candidates(project_root: str | Path, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """作者确认：候选写入锚点表（含 06 §8 默认越级规则）。既有文件一律拒绝覆盖。"""
    root = Path(project_root)
    if anchor_path(root).is_file():
        return {"ok": False, "error": "already_exists", "target": str(anchor_path(root))}
    anchor = load_anchor(root)
    anchor["境界链"] = [
        {
            "序": int(c.get("序", i + 1)),
            "名": str(c.get("名", "")),
            "差距描述": str(c.get("差距描述", "")),
            "寿元": str(c.get("寿元", "")),
        }
        for i, c in enumerate(candidates)
    ]
    write_anchor(root, anchor)
    append_events(
        root,
        [
            {
                "actor": "author",
                "action": "adopt",
                "domain": "战力",
                "path": ANCHOR_REL.as_posix(),
                "change_kind": "add",
                "diff_stat": {"ins": len(anchor["境界链"]), "del": 0},
                "summary": f"力量锚点表建立（{len(anchor['境界链'])} 级境界链）",
                "impact": [],
            }
        ],
    )
    return {"ok": True, "schema_version": ANCHOR_SCHEMA_VERSION, "chain": len(anchor["境界链"]), "target": str(anchor_path(root))}


# ---------------------------------------------------------------------------
# 境界链校验（doctor 语义：境界链序单调；06 §12-3）
# ---------------------------------------------------------------------------

def validate_chain(project_root: str | Path) -> list[str]:
    anchor = load_anchor(project_root)
    problems: list[str] = []
    chain = anchor.get("境界链") or []
    seen_names: dict[str, int] = {}
    for index, level in enumerate(chain, start=1):
        name = str(level.get("名", "")).strip()
        if not name:
            problems.append(f"境界链第 {index} 级：名缺失")
            continue
        if name in seen_names:
            problems.append(f"境界链重名：{name}（第 {seen_names[name]} 与第 {index} 级）")
        else:
            seen_names[name] = index
        try:
            order = int(level.get("序", 0))
        except (TypeError, ValueError):
            problems.append(f"境界链第 {index} 级：序非整数（{level.get('序')}）")
            continue
        if order != index:
            problems.append(f"境界链序不单调：第 {index} 级的序为 {order}")
    return problems


# ---------------------------------------------------------------------------
# 战例账本与 power_check（M4/T19，F-09：硬/软校验 + 通胀曲线 + 账本回写）
# ---------------------------------------------------------------------------

_BASIS_KEY_ORDER = ("金手指", "代价", "外因")
INFLATION_CONSECUTIVE_LIMIT = 2  # 连续超过该次数触发软提示
_DEVIATION_RE = re.compile(r"(?:提前|落后|延后)\s*(\d+)\s*章")


def _ordered_basis(basis: dict[str, str] | None) -> dict[str, str]:
    ordered = {key: str((basis or {}).get(key, "") or "") for key in _BASIS_KEY_ORDER}
    return {key: value for key, value in ordered.items() if value}


def record_battle(
    project_root: str | Path,
    *,
    chapter: int,
    matchup: str,
    result: str,
    cross: int,
    basis: dict[str, str] | None = None,
    foreshadowed: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """战例登记（data-agent 从正文提取后调用，作者可改）——即 F-09④ 账本回写。"""
    root = Path(project_root)
    anchor = load_anchor(root)
    for existing in anchor["战例账本"]:
        if int(existing.get("章", 0)) == int(chapter) and str(existing.get("对阵", "")) == str(matchup) and not force:
            return {"ok": False, "error": "duplicate", "chapter": int(chapter)}
    entry = {
        "章": int(chapter),
        "对阵": str(matchup),
        "结果": str(result),
        "跨阶": int(cross),
        "预告": bool(foreshadowed),
        "依据": _ordered_basis(basis),
    }
    anchor["战例账本"].append(entry)
    write_anchor(root, anchor)
    append_events(
        root,
        [
            {
                "actor": "ai",
                "action": "edit",
                "domain": "战力",
                "path": ANCHOR_REL.as_posix(),
                "change_kind": "add",
                "diff_stat": {"ins": 1, "del": 0},
                "summary": f"战例登记：第{int(chapter)}章 {matchup}（跨{int(cross)}阶）",
                "impact": [],
            }
        ],
    )
    return {"ok": True, "schema_version": ANCHOR_SCHEMA_VERSION, "entry": entry}


def record_inflation(
    project_root: str | Path,
    *,
    chapter: int,
    anchor_point: str,
    event: str,
    milestone: str,
    deviation: str,
) -> dict[str, Any]:
    """通胀记录追加（settle 时调用）：主角锚点事件 vs 卷纲里程碑的偏差。"""
    root = Path(project_root)
    anchor = load_anchor(root)
    entry = {
        "章": int(chapter),
        "主角锚点": str(anchor_point),
        "事件": str(event),
        "卷纲里程碑": str(milestone),
        "偏差": str(deviation),
    }
    anchor["通胀记录"].append(entry)
    write_anchor(root, anchor)
    append_events(
        root,
        [
            {
                "actor": "system",
                "action": "settle",
                "domain": "战力",
                "path": ANCHOR_REL.as_posix(),
                "change_kind": "add",
                "diff_stat": {"ins": 1, "del": 0},
                "summary": f"通胀记录追加：第{int(chapter)}章 {anchor_point} {event}（{deviation}）",
                "impact": [],
            }
        ],
    )
    return {"ok": True, "schema_version": ANCHOR_SCHEMA_VERSION, "entry": entry}


def _parse_deviation(raw: str) -> int:
    """偏差字符串 → 超前章数（提前N=+N；落后/延后N=-N；无法解析=0）。"""
    match = _DEVIATION_RE.search(str(raw or ""))
    if not match:
        return 0
    value = int(match.group(1))
    return -value if ("落后" in raw or "延后" in raw) else value


def power_check(project_root: str | Path, *, chapter: int | None = None) -> dict[str, Any]:
    """战力校验（F-09）：硬①依据完备性、硬②境界链矛盾（high+blocking）；
    软③通胀偏差连续超阈值（medium 提示）。结果可被 reviewer 作为证据源消费。"""
    anchor = load_anchor(project_root)
    chain_len = len(anchor.get("境界链") or [])
    battles = anchor.get("战例账本") or []
    if chapter is not None:
        battles = [b for b in battles if int(b.get("章", 0)) == int(chapter)]

    issues: list[dict[str, Any]] = []
    for battle in battles:
        chap = int(battle.get("章", 0))
        cross = int(battle.get("跨阶", 0) or 0)
        basis = battle.get("依据") or {}
        location = f"第{chap}章"
        evidence = f"{battle.get('对阵', '')}（{battle.get('结果', '')}）"
        if cross <= 0:
            continue
        if cross >= chain_len:
            issues.append(
                {
                    "severity": "high",
                    "category": "setting",
                    "location": location,
                    "description": f"境界链矛盾：跨{cross}阶超出链长 {chain_len}",
                    "evidence": evidence,
                    "fix_hint": "对齐境界链或下调跨阶数",
                    "blocking": True,
                }
            )
            continue
        if cross == 1:
            if not basis:
                issues.append(
                    {
                        "severity": "high",
                        "category": "setting",
                        "location": location,
                        "description": "越级无依据：跨1阶需列依据（金手指/代价/外因 任一）",
                        "evidence": evidence,
                        "fix_hint": "补充代价或外因，或改为同阶胜负",
                        "blocking": True,
                    }
                )
        else:
            missing = [key for key in ("金手指", "代价") if not basis.get(key)]
            if missing:
                issues.append(
                    {
                        "severity": "high",
                        "category": "setting",
                        "location": location,
                        "description": f"越级依据不完备：跨{cross}阶必须金手指+代价双列（缺 {'、'.join(missing)}）",
                        "evidence": evidence,
                        "fix_hint": "补齐依据并回填卷纲预告",
                        "blocking": True,
                    }
                )
            if not battle.get("预告"):
                issues.append(
                    {
                        "severity": "high",
                        "category": "setting",
                        "location": location,
                        "description": f"越级无预告：跨{cross}阶必须卷纲有预告（章纲卡战力事件）",
                        "evidence": evidence,
                        "fix_hint": "在章纲卡战力事件预告后再生效",
                        "blocking": True,
                    }
                )

    # 软③：通胀偏差（按章排序后）连续超阈值
    inflation = sorted(anchor.get("通胀记录") or [], key=lambda e: int(e.get("章", 0)))
    streak: list[dict[str, Any]] = []
    streaks: list[list[dict[str, Any]]] = []
    for entry in inflation + [{"章": 0, "偏差": "", "主角锚点": "", "事件": "", "卷纲里程碑": ""}]:
        deviation = abs(_parse_deviation(entry.get("偏差", "")))
        if deviation > INFLATION_THRESHOLD_CHAPTERS:
            streak.append(entry)
        else:
            if len(streak) >= INFLATION_CONSECUTIVE_LIMIT:
                streaks.append(streak)
            streak = []
    for run in streaks:
        chapters = "、".join(f"第{e.get('章')}章" for e in run)
        issues.append(
            {
                "severity": "medium",
                "category": "setting",
                "location": chapters,
                "description": f"战力通胀：偏差连续 {len(run)} 次超阈值（{INFLATION_THRESHOLD_CHAPTERS} 章）",
                "evidence": "；".join(f"{e.get('主角锚点')} {e.get('事件')}（{e.get('偏差')}）" for e in run),
                "fix_hint": "对账卷纲里程碑，放缓突破节奏",
                "blocking": False,
            }
        )

    high_count = sum(1 for issue in issues if issue["severity"] == "high")
    return {
        "ok": high_count == 0,
        "schema_version": ANCHOR_SCHEMA_VERSION,
        "battles_checked": len(battles),
        "chain_len": chain_len,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python -X utf8 power_anchor.py {extract|validate|battle|inflate|check} [options]"""
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="力量锚点与战力校验（T18/T19）")
    parser.add_argument("action", choices=["extract", "validate", "battle", "inflate", "check"])
    parser.add_argument("--apply", action="store_true", help="extract：作者确认写入锚点表")
    parser.add_argument("--chapter", type=int, default=None)
    parser.add_argument("--matchup", default="", help="对阵（A vs B）")
    parser.add_argument("--result", default="胜")
    parser.add_argument("--cross", type=int, default=0, help="跨阶数（0=同阶）")
    parser.add_argument("--basis", default="", help="依据，逗号分隔 键:值（金手指/代价/外因）")
    parser.add_argument("--foreshadowed", action="store_true", help="卷纲/章纲卡已有战力事件预告")
    parser.add_argument("--anchor-point", default="", help="通胀：主角锚点（如 凝罡(2)）")
    parser.add_argument("--event", default="", help="通胀：事件（如 突破）")
    parser.add_argument("--milestone", default="", help="通胀：卷纲里程碑")
    parser.add_argument("--deviation", default="", help="通胀：偏差（如 提前2章）")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    if args.action == "extract":
        report = extract_candidates(root)
        if report.get("ok") and args.apply:
            report = {**report, "applied": apply_candidates(root, report["candidates"])}
    elif args.action == "validate":
        problems = validate_chain(root)
        report = {"ok": not problems, "problems": problems}
    elif args.action == "battle":
        if not args.matchup or args.chapter is None:
            parser.error("battle 需要 --chapter 与 --matchup")
        basis = dict(
            part.split(":", 1) for part in args.basis.split(",") if part.strip() and ":" in part
        )
        basis = {k.strip(): v.strip() for k, v in basis.items()}
        report = record_battle(
            root,
            chapter=args.chapter,
            matchup=args.matchup,
            result=args.result,
            cross=args.cross,
            basis=basis,
            foreshadowed=args.foreshadowed,
        )
    elif args.action == "inflate":
        if args.chapter is None or not args.anchor_point:
            parser.error("inflate 需要 --chapter 与 --anchor-point")
        report = record_inflation(
            root,
            chapter=args.chapter,
            anchor_point=args.anchor_point,
            event=args.event,
            milestone=args.milestone,
            deviation=args.deviation,
        )
    else:
        report = power_check(root, chapter=args.chapter)

    if args.format == "json":
        print(_json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok", True) else 1

    if args.action == "extract":
        if not report.get("ok"):
            print(f"ERROR {report.get('error')}")
            return 1
        print(f"候选境界链（{report['source']}）：")
        for candidate in report["candidates"]:
            print(f"  {candidate['序']}. {candidate['名']}  {candidate['差距描述'] or '（无描述）'}")
        applied = report.get("applied")
        if applied is not None:
            print("OK 已写入锚点表" if applied.get("ok") else f"ERROR {applied.get('error')}")
        else:
            print("（候选未落盘；作者确认后加 --apply）")
    elif args.action == "validate":
        print("OK 境界链校验绿" if report["ok"] else "ERROR 境界链校验")
        for problem in report["problems"]:
            print(f"- {problem}")
    elif args.action in ("battle", "inflate"):
        print("OK 已登记" if report.get("ok") else f"ERROR {report.get('error')}")
    else:
        print("OK 战力校验通过" if report["ok"] else f"ERROR 战力校验：{sum(1 for i in report['issues'] if i['severity'] == 'high')} hard")
        for issue in report["issues"]:
            print(f"  [{issue['severity']}] {issue['location']}：{issue['description']}")
    return 0 if report.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
