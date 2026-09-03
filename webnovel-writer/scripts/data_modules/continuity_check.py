"""连贯性检查：时间线年龄推演（A4）与命名冲突检查（A5）。

webnovel-copilot-300 · M6/T29。

- 年龄推演：时间锚「…第N天/日」解析为故事内天数，以 book.yaml `主角年龄`（基准
  年龄）与 `觉醒日`（修龄起算日，默认 1）为锚，推算每章「主角年龄/修龄」列——
  年龄 = 基准 + (天数-觉醒日)//365；修龄 = max(0, 天数-觉醒日)。未配置基准或锚
  不可解析时输出「—」，不加列、不猜数。
- 命名冲突：新名字 vs 名册正名/别名（v7 名册 front matter + 名册.md 表）做
  编辑距离（Levenshtein）+ 相似度 + 包含关系三重检查，撞名/近名全数报出
  （data-agent 新实体登记前必须调用）。
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any

CONTINUITY_SCHEMA_VERSION = "continuity-check/1"
_ANCHOR_DAY_RE = re.compile(r"第\s*(\d{1,5})\s*[天日]")
_NAME_RE = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9]{2,8}")


# ---------------------------------------------------------------------------
# A4：时间线年龄/修龄推演
# ---------------------------------------------------------------------------

def parse_anchor_day(anchor: str) -> int | None:
    """时间锚 → 故事内天数（「第N天/日」；解析失败 None）。"""
    match = _ANCHOR_DAY_RE.search(str(anchor or ""))
    return int(match.group(1)) if match else None


def _book_age_base(project_root: Path) -> dict[str, int] | None:
    book_yaml = project_root / "book.yaml"
    if not book_yaml.is_file():
        return None
    text = book_yaml.read_text(encoding="utf-8")
    age_match = re.search(r"^主角年龄:\s*(\d+)", text, re.MULTILINE)
    if not age_match:
        return None
    day_match = re.search(r"^觉醒日:\s*(\d+)", text, re.MULTILINE)
    return {"base_age": int(age_match.group(1)), "base_day": int(day_match.group(1)) if day_match else 1}


def _view_rows(project_root: Path, volume: int) -> list[dict[str, Any]]:
    view = project_root / "大纲" / "卷纲" / f"第{volume:02d}卷-时间线.md"
    if not view.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in view.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\|\s*(\d{1,4})\s*\|\s*(.*?)\s*\|", line.strip())
        if match:
            rows.append({"章": int(match.group(1)), "锚": match.group(2)})
    return rows


def derive_age_columns(project_root: str | Path, *, volume: int) -> list[dict[str, Any]]:
    """时间线视图的年龄/修龄列数据（无基准配置返回空列表；从已落盘视图读取）。"""
    root = Path(project_root)
    base = _book_age_base(root)
    if base is None:
        return []
    rows = [(row["章"], row["锚"]) for row in _view_rows(root, volume)]
    return build_age_columns(rows, base)


def build_age_columns(rows: list[tuple[int, str]], base: dict[str, int]) -> list[dict[str, Any]]:
    """核心推演：[(章, 时间锚)] → [{章, 年龄, 修龄}]（锚不可解析为「—」）。"""
    columns: list[dict[str, Any]] = []
    for chapter, anchor in rows:
        day = parse_anchor_day(anchor)
        if day is None:
            columns.append({"章": int(chapter), "年龄": "—", "修龄": "—"})
            continue
        age = base["base_age"] + max(0, day - base["base_day"]) // 365
        cultivation_age = max(0, day - base["base_day"])
        columns.append({"章": int(chapter), "年龄": age, "修龄": cultivation_age})
    return columns


# ---------------------------------------------------------------------------
# A5：命名冲突检查（编辑距离 + 相似度 + 包含）
# ---------------------------------------------------------------------------

def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def load_known_names(project_root: str | Path) -> list[dict[str, str]]:
    """已知名字池：v7 名册 front matter（正名+别名 JSON）+ 名册.md 总表（中文名单元格）。"""
    root = Path(project_root)
    known: list[dict[str, str]] = []
    roster_dir = root / "定稿" / "设定" / "名册"
    if roster_dir.is_dir():
        for path in sorted(roster_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            if not text.startswith("---"):
                continue
            head = text.split("---", 2)
            if len(head) < 3:
                continue
            canonical = ""
            aliases: list[str] = []
            for line in head[1].splitlines():
                if line.startswith("正名:"):
                    canonical = line.partition(":")[2].strip()
                elif line.startswith("别名:"):
                    raw = line.partition(":")[2].strip()
                    try:
                        aliases = [str(a) for a in json.loads(raw)] if raw else []
                    except json.JSONDecodeError:
                        aliases = [raw.strip("[]\" ")] if raw else []
            if canonical:
                known.append({"name": canonical, "alias": "", "source": path.name})
            for alias in aliases:
                if alias:
                    known.append({"name": alias, "alias": canonical, "source": path.name})
    # 名册.md 总表（历史形态：列对齐不稳，直接取行内的中文名单元格）
    roster_md = root / "定稿" / "设定" / "名册.md"
    if roster_md.is_file():
        seen = {k["name"] for k in known}
        for line in roster_md.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("|") or set(line) <= {"|", "-", " ", ":"}:
                continue
            for cell in line.strip("|").split("|"):
                cell = cell.strip()
                if cell and _NAME_RE.fullmatch(cell) and cell not in seen and cell not in ("正名", "别名", "首现章"):
                    known.append({"name": cell, "alias": "", "source": "名册.md"})
                    seen.add(cell)
    return known


def check_name_conflicts(
    project_root: str | Path,
    name: str,
    *,
    ratio_threshold: float = 0.72,
) -> dict[str, Any]:
    """新名字 vs 已知名字池：编辑距离 ≤ max(1, 短名长//2) 或相似度 ≥ 阈值 或包含 → 撞名。"""
    name = str(name or "").strip()
    if not name:
        return {"ok": False, "error": "missing_name", "conflicts": []}
    conflicts: list[dict[str, Any]] = []
    for known in load_known_names(project_root):
        other = known["name"]
        distance = _levenshtein(name, other)
        ratio = round(difflib.SequenceMatcher(None, name, other).ratio(), 2)
        contains = (name in other or other in name) and name != other
        if distance == 0 or contains or distance <= max(1, min(len(name), len(other)) // 2) or ratio >= ratio_threshold:
            conflicts.append(
                {
                    "name": other,
                    "alias_of": known["alias"],
                    "distance": distance,
                    "ratio": ratio,
                    "matched_via": known["source"],
                }
            )
    conflicts.sort(key=lambda c: (c["distance"], -c["ratio"]))
    return {
        "ok": True,
        "schema_version": CONTINUITY_SCHEMA_VERSION,
        "name": name,
        "checked": len(load_known_names(project_root)),
        "conflicts": conflicts,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python -X utf8 continuity_check.py --name X [--format json]

    一般经 `webnovel.py name-check --name X` 调用（data-agent 新实体登记前必跑）。
    """
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="年龄推演与命名冲突检查（T29）")
    parser.add_argument("--name", default="", help="待检新名字")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    if not args.name:
        parser.error("需要 --name")
    report = check_name_conflicts(root, args.name)

    if args.format == "json":
        print(_json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok", True) else 1

    if not report.get("ok"):
        print(f"ERROR {report.get('error')}")
        return 1
    if report["conflicts"]:
        print(f"撞名 {len(report['conflicts'])} 处：")
        for conflict in report["conflicts"]:
            alias = f"（{conflict['alias_of']} 的别名）" if conflict["alias_of"] else ""
            print(
                f"  {conflict['name']}{alias}：编辑距离 {conflict['distance']}，相似度 {conflict['ratio']}"
            )
    else:
        print("OK 无撞名")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
