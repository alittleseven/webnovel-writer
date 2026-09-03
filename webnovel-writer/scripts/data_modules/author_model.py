"""作者模型数据面（webnovel-copilot-300 · M3/T16，06 §5 / F-12）。

双层模型：
- 项目层 `作者/author_model.md`：LLM/作者维护（06 §5 四段骨架：节奏偏好/雷点/
  修改习惯/当前书特定要求），作者随时可改（改动走 journal）。
- 用户层 `作者/跨书偏好.yaml`：节奏/雷点/审稿习惯——其中
  `审稿习惯.接受AI建议率` 由脚本按 journal adopt/discard 统计维护。

学习闭环（F-12，被动为主）：
- `learn_from_journal`：卷级归纳（0 token 脚本统计）→ 生成
  `作者/author_model-建议.md`（含证据），**作者确认后才 apply**。
- `apply_suggestion`：确认后的建议追加进 author_model.md（带「已确认」标记）
  并回写跨书偏好统计（双层回写）。
- `load_author_model_section`：context 装配注入形态（context_manager 消费）。

红线：learn 不改 author_model.md；单章级高频信号只做统计不进 LLM（token 纪律）。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .author_journal import append_events, read_journal_view
from .material_review import _chapters_per_volume

MODEL_SCHEMA_VERSION = "author-model/1"
MODEL_REL = Path("作者") / "author_model.md"
SUGGESTION_REL = Path("作者") / "author_model-建议.md"
PREFERENCES_REL = Path("作者") / "跨书偏好.yaml"
MODEL_SECTIONS = ("节奏偏好", "雷点", "修改习惯", "当前书特定要求")
_CHAPTER_IN_PATH = re.compile(r"(\d{3,4})")
_TOP_PATHS_LIMIT = 5


def _utc_today() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")


def model_path(project_root: str | Path) -> Path:
    return Path(project_root) / MODEL_REL


def suggestion_path(project_root: str | Path) -> Path:
    return Path(project_root) / SUGGESTION_REL


def preferences_path(project_root: str | Path) -> Path:
    return Path(project_root) / PREFERENCES_REL


def _chapter_of_event(event: dict[str, Any]) -> int | None:
    path = str(event.get("path") or "")
    if any(token in path for token in ("章纲", "正文", "条目", "卷纲")):
        match = _CHAPTER_IN_PATH.search(path)
        if match:
            return int(match.group(1))
    return None


def learn_from_journal(
    project_root: str | Path,
    *,
    volume: int | None = None,
    chapters_per_volume: int | None = None,
) -> dict[str, Any]:
    """卷级归纳（0 token）：journal 统计 → 建议文件。不改 author_model.md。"""
    root = Path(project_root)
    cpv = chapters_per_volume or _chapters_per_volume(root)
    events = read_journal_view(root)
    in_scope: list[dict[str, Any]] = []
    for event in events:
        chapter = _chapter_of_event(event)
        if volume is not None:
            # 卷口径只统计有章锚点且落在该卷的事件（无锚点事件属全书活动，避免每卷重复计入）
            if chapter is None or (chapter - 1) // max(cpv, 1) + 1 != int(volume):
                continue
        in_scope.append(event)

    by_domain: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    path_counts: dict[str, int] = {}
    pet_peeves: list[str] = []
    action_counts: dict[str, int] = {}
    ins_total = del_total = 0
    for event in in_scope:
        domain = str(event.get("domain") or "其他")
        kind = str(event.get("change_kind") or "content")
        action = str(event.get("action") or "edit")
        by_domain[domain] = by_domain.get(domain, 0) + 1
        by_kind[kind] = by_kind.get(kind, 0) + 1
        action_counts[action] = action_counts.get(action, 0) + 1
        path_value = str(event.get("path") or "")
        if path_value:
            path_counts[path_value] = path_counts.get(path_value, 0) + 1
        diff = event.get("diff_stat") or {}
        ins_total += int(diff.get("ins") or 0)
        del_total += int(diff.get("del") or 0)
        if kind == "delete" or int(diff.get("del") or 0) > int(diff.get("ins") or 0):
            summary = str(event.get("summary") or "").strip()
            if summary:
                pet_peeves.append(f"- {summary}（{path_value}）")

    top_paths = sorted(path_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:_TOP_PATHS_LIMIT]
    lines: list[str] = [
        f"# author_model 归纳建议（{'卷' + str(volume) if volume is not None else '全书'}口径，生成于 {_utc_today()}）",
        "",
        f"> 事件范围：{len(in_scope)}/{len(events)} 条；增 {ins_total} 行 / 删 {del_total} 行；采纳 {action_counts.get('adopt', 0)} / 丢弃 {action_counts.get('discard', 0)}",
        f"> 域分布：{json_dumps_cn(by_domain)}；修改类型：{json_dumps_cn(by_kind)}",
        "",
    ]
    lines.append("## 节奏偏好")
    lines.append("- （待 LLM 归纳：高频编辑域与时机见上方分布）")
    lines.append("")
    lines.append("## 雷点（作者改掉过什么）")
    lines.extend(pet_peeves[:10] if pet_peeves else ["- （无删除型修改证据）"])
    lines.append("")
    lines.append("## 修改习惯")
    lines.append(f"- 高频修改路径：{'；'.join(f'{p}（{c} 次）' for p, c in top_paths) or '（无）'}")
    lines.append("")
    lines.append("## 当前书特定要求")
    lines.append("- （待作者/会话补充）")
    lines.append("")

    target = suggestion_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    append_events(
        root,
        [
            {
                "actor": "ai",
                "action": "learn",
                "domain": "其他",
                "path": SUGGESTION_REL.as_posix(),
                "change_kind": "add",
                "diff_stat": {"ins": len(lines), "del": 0},
                "summary": f"journal 归纳建议生成（{'卷' + str(volume) if volume is not None else '全书'}，{len(in_scope)} 事件）",
                "impact": [],
            }
        ],
    )
    return {
        "ok": True,
        "schema_version": MODEL_SCHEMA_VERSION,
        "events_scanned": len(events),
        "events_in_scope": len(in_scope),
        "suggestion": str(target),
        "pet_peeves": len(pet_peeves),
        "chapters_per_volume": cpv,
    }


def apply_suggestion(project_root: str | Path, *, suggestion_file: str | Path | None = None) -> dict[str, Any]:
    """作者确认后的双层回写：建议追加进 author_model.md + 跨书偏好统计更新。"""
    root = Path(project_root)
    source = Path(suggestion_file) if suggestion_file else suggestion_path(root)
    if not source.is_file():
        return {"ok": False, "error": "suggestion_missing", "suggestion": str(source)}
    content = source.read_text(encoding="utf-8").strip()
    if not content:
        return {"ok": False, "error": "suggestion_empty", "suggestion": str(source)}

    model = model_path(root)
    model.parent.mkdir(parents=True, exist_ok=True)
    if not model.is_file():
        skeleton = [f"# 作者模型（{MODEL_SCHEMA_VERSION}）", ""]
        for section in MODEL_SECTIONS:
            skeleton.extend([f"## {section}", "- （待归纳）", ""])
        skeleton.append("---")
        model.write_text("\n".join(skeleton) + "\n", encoding="utf-8", newline="\n")

    with model.open("a", encoding="utf-8", newline="\n") as file:
        file.write(f"\n## {_utc_today()} 归纳（已确认）\n\n{content}\n")

    preferences = _recompute_acceptance_rate(root)
    write_preferences(root, preferences)

    append_events(
        root,
        [
            {
                "actor": "author",
                "action": "learn",
                "domain": "文风",
                "path": MODEL_REL.as_posix(),
                "change_kind": "add",
                "diff_stat": {"ins": 1, "del": 0},
                "summary": "归纳建议确认并回写 author_model + 跨书偏好",
                "impact": [],
            }
        ],
    )
    return {"ok": True, "schema_version": MODEL_SCHEMA_VERSION, "model": str(model), "preferences": str(preferences_path(root))}


def load_author_model_section(project_root: str | Path) -> dict[str, str]:
    """context 装配注入形态（F-12：author_model + 跨书偏好进上下文）。缺失返回空串。"""
    root = Path(project_root)
    model_text = model_path(root).read_text(encoding="utf-8") if model_path(root).is_file() else ""
    pref_text = preferences_path(root).read_text(encoding="utf-8") if preferences_path(root).is_file() else ""
    return {"模型要点": model_text.strip(), "跨书偏好": pref_text.strip()}


# ---------------------------------------------------------------------------
# 跨书偏好.yaml（用户层；内置最小读写器，固定 schema）
# ---------------------------------------------------------------------------

_PREFERENCES_DEFAULT: dict[str, Any] = {
    "节奏": {"冲突前置": True, "章末必留钩": True},
    "雷点": [],
    "审稿习惯": {"偏好裁决选项数": 3, "接受AI建议率": 0.0},
}


def read_preferences(project_root: str | Path) -> dict[str, Any]:
    path = preferences_path(project_root)
    if not path.is_file():
        return _deep_copy(_PREFERENCES_DEFAULT)
    result: dict[str, Any] = {}
    section: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0:
            key, _, value = line.partition(":")
            if value.strip() == "":
                section = key.strip()
                result[section] = {}
            else:
                section = None
                result[key.strip()] = _parse_pref_scalar(value.strip())
        else:
            key, _, value = line.partition(":")
            if section is not None:
                result[section][key.strip()] = _parse_pref_scalar(value.strip())
    return _merge_defaults(result)


def write_preferences(project_root: str | Path, preferences: dict[str, Any]) -> Path:
    path = preferences_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for section, value in preferences.items():
        if isinstance(value, dict):
            lines.append(f"{section}:")
            for key, item in value.items():
                lines.append(f"  {key}: {_emit_pref_scalar(item)}")
        elif isinstance(value, list):
            lines.append(f"{section}:")
            for item in value:
                lines.append(f"  - {_emit_pref_scalar(item)}")
        else:
            lines.append(f"{section}: {_emit_pref_scalar(value)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _recompute_acceptance_rate(project_root: Path) -> dict[str, Any]:
    preferences = read_preferences(project_root)
    events = read_journal_view(project_root)
    adopted = sum(1 for e in events if e.get("action") == "adopt")
    discarded = sum(1 for e in events if e.get("action") == "discard")
    total = adopted + discarded
    preferences.setdefault("审稿习惯", {})["接受AI建议率"] = round(adopted / total, 2) if total else 0.0
    return preferences


def _parse_pref_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
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


def _emit_pref_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return str(value)


def _merge_defaults(partial: dict[str, Any]) -> dict[str, Any]:
    merged = _deep_copy(_PREFERENCES_DEFAULT)
    for section, value in partial.items():
        if isinstance(value, dict) and isinstance(merged.get(section), dict):
            merged[section].update(value)
        else:
            merged[section] = value
    return merged


def _deep_copy(source: dict[str, Any]) -> dict[str, Any]:
    return {key: (dict(val) if isinstance(val, dict) else list(val) if isinstance(val, list) else val) for key, val in source.items()}


def json_dumps_cn(payload: dict[str, int]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python -X utf8 author_model.py {learn|apply|show}

    一般经 `webnovel.py learn --from-journal` 调用（F-12）。
    """
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="作者模型数据面（T16）")
    parser.add_argument("action", choices=["learn", "apply", "show"])
    parser.add_argument("--from-journal", action="store_true", help="learn 数据源（F-12 固定为 journal）")
    parser.add_argument("--volume", type=int, default=None, help="卷级归纳口径")
    parser.add_argument("--suggestion", default="", help="apply 的建议文件（缺省 作者/author_model-建议.md）")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    if args.action == "learn":
        if not args.from_journal:
            parser.error("learn 需要 --from-journal（F-12 数据源唯一）")
        report = learn_from_journal(root, volume=args.volume)
    elif args.action == "apply":
        report = apply_suggestion(root, suggestion_file=args.suggestion or None)
    else:
        report = {"ok": True, **load_author_model_section(root)}

    if args.format == "json":
        print(_json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok", True) else 1

    if args.action == "learn":
        print(f"OK 归纳建议生成：{report['events_in_scope']}/{report['events_scanned']} 事件 → {report['suggestion']}")
    elif args.action == "apply":
        if not report.get("ok"):
            print(f"ERROR {report.get('error')}")
        else:
            print(f"OK 已回写 {report['model']} 与 {report['preferences']}")
    else:
        print(f"模型要点：{report['模型要点'][:80] or '（空）'}…")
        print(f"跨书偏好：{report['跨书偏好'][:80] or '（空）'}…")
    return 0 if report.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
