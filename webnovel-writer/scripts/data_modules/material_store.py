"""素材数据面（webnovel-copilot-300 · M2/T11，流程 F-05）。

素材三层流转：`素材/活/*.csv`（活层，作者可编辑）→ freeze 快照 `素材/定版/v{NN}/`
→ 写作装配只取「定版（带版本）+ 活层 active top-K」。10 张表与列约定见
docs/zcode/webnovel-copilot-300/06-data-design.md §7：
统一列骨架 `id,名称,分类,核心摘要,详细展开,正例,反例,来源,状态,备注`（各表可加专属列）。

- `来源`：作者手写 | AI归纳 | 拆书:<出处> | 工坊采纳:<提案id> | 播种:<题材包>
- `状态`：active | 衰减（N 卷未用）| 归档——material-review（T14）维护
- init 播种（D0-5）：按题材子集复制 references/csv 到 4 张核心表，每表 ≤30 条；
  既有表一律不覆盖（作者主权 P1/P2）。
红线：读容错（utf-8-sig/BOM）；写不破坏既有行；装配不写任何文件。
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .author_journal import append_events

MATERIAL_SCHEMA_VERSION = "material/1"
MATERIAL_TABLES: tuple[str, ...] = (
    "桥段", "爽点节奏", "人设关系", "场景写法", "写作技法",
    "命名风格", "金手指零件", "世界观零件", "台词金句", "梗与反差",
)
SKELETON_COLUMNS: tuple[str, ...] = (
    "id", "名称", "分类", "核心摘要", "详细展开", "正例", "反例", "来源", "状态", "备注",
)
STATUS_VALUES: tuple[str, ...] = ("active", "衰减", "归档")
SOURCE_PATTERN = re.compile(r"^(作者手写|AI归纳|拆书:.+|工坊采纳:.+|播种:.+)$")
DEFAULT_SEED_TABLES: tuple[str, ...] = ("桥段", "爽点节奏", "人设关系", "写作技法")
SEED_PER_TABLE_LIMIT = 30
ASSEMBLY_TOP_K_DEFAULT = 20

# 播种源映射：素材表 → (references/csv 源文件, 名称列, 正例列, 反例列)
TABLE_SOURCES: dict[str, dict[str, str]] = {
    "桥段": {"file": "桥段套路.csv", "名称": "桥段名称", "正例": "核心爽点", "反例": "毒点"},
    "爽点节奏": {"file": "爽点与节奏.csv", "名称": "节奏类型", "正例": "情绪调动手法", "反例": "毒点"},
    "人设关系": {"file": "人设与关系.csv", "名称": "人设类型", "正例": "互动模式", "反例": "毒点"},
    "场景写法": {"file": "场景写法.csv", "名称": "模式名称", "正例": "示例片段", "反例": "毒点"},
    "写作技法": {"file": "写作技法.csv", "名称": "技法名称", "正例": "正例", "反例": "反例"},
    "命名风格": {"file": "命名规则.csv", "名称": "规则", "正例": "正例", "反例": "反例"},
    "金手指零件": {"file": "金手指与设定.csv", "名称": "设定类型", "正例": "与剧情交互方式", "反例": "毒点"},
}

# D0-5 题材子集：canonical 题材键 → 参考库「适用题材」列关键词（命中或「全部」的行入选）
_GENRE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "xianxia": ("玄幻", "仙侠"),
    "urban-power": ("都市",),
    "romance": ("现言", "古言", "幻言"),
    "mystery": ("悬疑",),
    "rules-mystery": ("悬疑", "科幻"),
    "substitute": ("现言", "古言", "快穿"),
    "esports": ("游戏",),
    "livestream": ("都市",),
    "cosmic-horror": ("科幻", "悬疑"),
}


# 引用短名归一（06 §2 示例用短名：素材引用: [桥段:TR-012, 场景:SP-007]）
TABLE_ALIASES: dict[str, str] = {
    "桥段": "桥段", "爽点": "爽点节奏", "爽点节奏": "爽点节奏",
    "人设": "人设关系", "人设关系": "人设关系",
    "场景": "场景写法", "场景写法": "场景写法",
    "技法": "写作技法", "写作技法": "写作技法",
    "命名": "命名风格", "命名风格": "命名风格",
    "金手指": "金手指零件", "金手指零件": "金手指零件",
    "世界观": "世界观零件", "世界观零件": "世界观零件",
    "金句": "台词金句", "台词金句": "台词金句",
    "梗": "梗与反差", "梗与反差": "梗与反差",
}


def normalize_table(name: str) -> str | None:
    """表短名/全名 → 规范表名；未知返回 None。"""
    return TABLE_ALIASES.get(str(name).strip())


def material_dir(project_root: str | Path) -> Path:
    return Path(project_root) / "素材" / "活"


def material_csv_path(project_root: str | Path, table: str) -> Path:
    return material_dir(project_root) / f"{table}.csv"


def default_source_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "references" / "csv"


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [
            {k: (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(file)
            if any((v or "").strip() for v in row.values())
        ]


def read_table(project_root: str | Path, table: str, *, include_archived: bool = False) -> list[dict[str, str]]:
    """读活层表（默认排除归档行；空/坏表返回 []）。"""
    rows = _read_csv_rows(material_csv_path(project_root, table))
    if include_archived:
        return rows
    return [row for row in rows if row.get("状态") != "归档"]


def append_entries(
    project_root: str | Path,
    table: str,
    entries: list[dict[str, Any]],
    *,
    source: str = "作者手写",
    journal_summary: str = "",
) -> dict[str, Any]:
    """向活层表追加条目（补齐骨架列；id 冲突拒绝）。留 journal(edit, domain=素材)。"""
    if table not in MATERIAL_TABLES:
        return {"ok": False, "error": "unknown_table", "table": table}
    path = material_csv_path(project_root, table)
    existing = _read_csv_rows(path)
    existing_ids = {row.get("id", "") for row in existing}
    normalized: list[dict[str, str]] = []
    for entry in entries:
        entry_id = str(entry.get("id") or "").strip()
        if not entry_id:
            return {"ok": False, "error": "missing_id", "table": table}
        if entry_id in existing_ids:
            return {"ok": False, "error": "duplicate_id", "table": table, "id": entry_id}
        existing_ids.add(entry_id)
        row = {col: str(entry.get(col, "") or "") for col in SKELETON_COLUMNS}
        row["id"], row["来源"], row["状态"] = entry_id, source, "active"
        normalized.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(SKELETON_COLUMNS)
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if not existing:
            writer.writeheader()
        writer.writerows(normalized)
    append_events(
        project_root,
        [
            {
                "actor": "system",
                "action": "edit",
                "domain": "素材",
                "path": f"素材/活/{table}.csv",
                "change_kind": "add",
                "diff_stat": {"ins": len(normalized), "del": 0},
                "summary": journal_summary or f"{table} 表新增 {len(normalized)} 条（来源 {source}）",
                "impact": [],
            }
        ],
    )
    return {"ok": True, "table": table, "appended": len(normalized), "schema_version": MATERIAL_SCHEMA_VERSION}


def validate_tables(project_root: str | Path) -> list[str]:
    """全表校验：id 重复 / 状态非法 / 来源非法 / id 缺失。返回问题描述列表。"""
    problems: list[str] = []
    for table in MATERIAL_TABLES:
        seen: dict[str, int] = {}
        for index, row in enumerate(_read_csv_rows(material_csv_path(project_root, table)), start=2):
            row_id = row.get("id", "")
            label = f"{table}.csv#{row_id or f'行{index}'}"
            if not row_id:
                problems.append(f"{label}: id 缺失")
                continue
            if row_id in seen:
                problems.append(f"{label}: id 重复（首次见第 {seen[row_id]} 行）")
            else:
                seen[row_id] = index
            status = row.get("状态", "")
            if status and status not in STATUS_VALUES:
                problems.append(f"{label}: 状态非法（{status}）")
            source = row.get("来源", "")
            if source and not SOURCE_PATTERN.match(source):
                problems.append(f"{label}: 来源非法（{source}）")
    return problems


# ---------------------------------------------------------------------------
# 装配选择器（F-05：定版带版本 + 活层 active top-K；只读）
# ---------------------------------------------------------------------------

def latest_frozen_version(project_root: str | Path) -> int | None:
    definitive = Path(project_root) / "素材" / "定版"
    if not definitive.is_dir():
        return None
    versions = [
        int(match.group(1))
        for entry in definitive.iterdir()
        if entry.is_dir() and (match := re.fullmatch(r"v(\d+)", entry.name))
    ]
    return max(versions) if versions else None


def read_frozen_table(project_root: str | Path, table: str, version: int) -> list[dict[str, str]]:
    return _read_csv_rows(Path(project_root) / "素材" / "定版" / f"v{int(version):02d}" / f"{table}.csv")


def _usage_counts(project_root: str | Path) -> dict[str, int]:
    path = Path(project_root) / "素材" / "使用轨迹.jsonl"
    if not path.is_file():
        return {}
    counts: dict[str, int] = {}
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                entry_id = json.loads(line).get("条目id")
            except json.JSONDecodeError:
                continue
            if entry_id:
                counts[entry_id] = counts.get(entry_id, 0) + 1
    return counts


def assemble_materials(
    project_root: str | Path,
    *,
    tables: list[str] | tuple[str, ...] | None = None,
    k: int = ASSEMBLY_TOP_K_DEFAULT,
    version: int | None = None,
) -> dict[str, Any]:
    """写作装配素材选择（只读）。

    frozen = 定版快照全量（带版本号，默认最新卷）；live = 活层 active 行按
    （使用次数升序，id 升序）排序取 top-K——未被用过的条目优先获得曝光。
    归档与衰减条目不进装配。
    """
    selected = list(tables) if tables else list(MATERIAL_TABLES)
    frozen_version = version if version is not None else latest_frozen_version(project_root)
    usage = _usage_counts(project_root)

    frozen: dict[str, dict[str, Any]] = {}
    live: dict[str, list[dict[str, str]]] = {}
    for table in selected:
        if frozen_version is not None:
            rows = read_frozen_table(project_root, table, frozen_version)
            if rows:
                frozen[table] = {"version": frozen_version, "rows": rows}
        active = [row for row in read_table(project_root, table) if row.get("状态") == "active"]
        active.sort(key=lambda row: (usage.get(row.get("id", ""), 0), row.get("id", "")))
        if active:
            live[table] = active[: max(int(k), 0)]
    return {
        "schema_version": MATERIAL_SCHEMA_VERSION,
        "frozen": frozen,
        "live": live,
        "k": int(k),
        "frozen_version": frozen_version,
    }


# ---------------------------------------------------------------------------
# init 播种（D0-5：题材子集 ≈4 表 × ≤30 条）
# ---------------------------------------------------------------------------

def _genre_keywords(genre: str) -> set[str]:
    keys = {part.strip() for part in re.split(r"[+|/、,，\s]+", str(genre or "")) if part.strip()}
    keywords: set[str] = set()
    for key in keys:
        keywords.update(_GENRE_KEYWORDS.get(key, (key,)))
    return keywords


def _seed_rows_for_table(source_dir: Path, table: str, keywords: set[str], limit: int) -> list[dict[str, str]]:
    mapping = TABLE_SOURCES.get(table)
    if mapping is None:
        return []
    source_path = source_dir / mapping["file"]
    if not source_path.is_file():
        return []
    rows: list[dict[str, str]] = []
    for raw in _read_csv_rows(source_path):
        applicable = {part.strip() for part in re.split(r"[|/、,，\s]+", raw.get("适用题材", "")) if part.strip()}
        if keywords and "全部" not in applicable and not (applicable & keywords):
            continue
        fallback_example = raw.get(mapping["正例"]) or raw.get("大模型指令", "")
        fallback_anti = raw.get(mapping["反例"]) or raw.get("核心摘要", "")
        rows.append(
            {
                "id": raw.get("编号", ""),
                "名称": raw.get(mapping["名称"], ""),
                "分类": raw.get("分类", ""),
                "核心摘要": raw.get("核心摘要", ""),
                "详细展开": raw.get("详细展开", ""),
                "正例": fallback_example,
                "反例": fallback_anti,
                "来源": "",
                "状态": "active",
                "备注": f"播种自:{mapping['file']}",
            }
        )
        if len(rows) >= limit:
            break
    return rows


def seed_materials(
    project_root: str | Path,
    *,
    genre: str,
    tables: list[str] | tuple[str, ...] | None = None,
    per_table_limit: int = SEED_PER_TABLE_LIMIT,
    source_dir: str | Path | None = None,
) -> dict[str, Any]:
    """按题材子集播种活层（只建缺失表；既有表一律跳过，返回 skipped）。"""
    root = Path(project_root)
    src = Path(source_dir) if source_dir else default_source_dir()
    keywords = _genre_keywords(genre)
    selected = list(tables) if tables else list(DEFAULT_SEED_TABLES)

    seeded: dict[str, int] = {}
    rows_by_table: dict[str, list[dict[str, str]]] = {}
    skipped: list[str] = []
    for table in selected:
        if table not in MATERIAL_TABLES:
            skipped.append(table)
            continue
        target = material_csv_path(root, table)
        if target.is_file():
            skipped.append(table)
            continue
        rows = _seed_rows_for_table(src, table, keywords, per_table_limit)
        if not rows:
            skipped.append(table)
            continue
        for row in rows:
            row["来源"] = f"播种:{genre}"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(SKELETON_COLUMNS))
            writer.writeheader()
            writer.writerows(rows)
        seeded[table] = len(rows)
        rows_by_table[table] = rows

    if seeded:
        append_events(
            root,
            [
                {
                    "actor": "system",
                    "action": "edit",
                    "domain": "素材",
                    "path": "素材/活/",
                    "change_kind": "add",
                    "diff_stat": {"ins": sum(seeded.values()), "del": 0},
                    "summary": f"init 播种素材 {sum(seeded.values())} 条（题材 {genre}，{len(seeded)} 表）",
                    "impact": [],
                }
            ],
        )
    return {
        "ok": True,
        "genre": genre,
        "seeded": seeded,
        "rows": rows_by_table,
        "skipped": skipped,
        "schema_version": MATERIAL_SCHEMA_VERSION,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python -X utf8 material_store.py {list|validate|assemble|seed|log|trajectory|propose|candidates|adopt|discard|review|apply-ruling} [options]

    M2 统一素材 CLI：T12 log/trajectory（material_usage）、T13 propose/candidates/adopt/discard
    （material_intake）、T14 review/apply-ruling（material_review）经此分发。
    """
    import argparse

    parser = argparse.ArgumentParser(description="素材工作台（T11-T14）")
    parser.add_argument(
        "action",
        choices=["list", "validate", "assemble", "seed", "log", "trajectory", "propose", "candidates", "adopt", "discard", "review", "apply-ruling"],
    )
    parser.add_argument("--table", action="append", default=[], help="限定表（可重复）")
    parser.add_argument("--k", type=int, default=ASSEMBLY_TOP_K_DEFAULT)
    parser.add_argument("--version", type=int, default=None)
    parser.add_argument("--genre", default="")
    parser.add_argument("--source-dir", default="")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    # T12 轨迹参数
    parser.add_argument("--chapter", type=int, default=None)
    parser.add_argument("--usage", default="章纲引用")
    parser.add_argument("--force", action="store_true")
    # T13 入库参数
    parser.add_argument("--channel", default="", help="AI归纳 | 拆书:<出处>")
    parser.add_argument("--file", default="", help="候选条目 CSV 文件")
    parser.add_argument("--batch", default="", help="画廊批次文件名")
    parser.add_argument("--ids", default="", help="逗号分隔条目 id（adopt 限定；缺省整批）")
    # T14 审阅参数
    parser.add_argument("--volume", type=int, default=None)
    parser.add_argument("--decay-volumes", type=int, default=1)
    parser.add_argument("--ruling", action="append", default=[], help="裁决 表:ID:动作[:并入ID]（可重复）")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    tables = args.table or None

    if args.action in ("log", "trajectory"):
        from . import material_usage

        sub_argv = [args.action, "--project-root", str(root), "--format", args.format]
        if args.chapter is not None:
            sub_argv.extend(["--chapter", str(args.chapter)])
        if args.action == "log":
            sub_argv.extend(["--usage", args.usage])
            if args.force:
                sub_argv.append("--force")
        return material_usage.main(sub_argv)

    if args.action in ("propose", "candidates", "adopt", "discard"):
        from . import material_intake

        sub_argv = [args.action, "--project-root", str(root), "--format", args.format]
        if args.channel:
            sub_argv.extend(["--channel", args.channel])
        if args.file:
            sub_argv.extend(["--file", args.file])
        if args.batch:
            sub_argv.extend(["--batch", args.batch])
        if args.ids:
            sub_argv.extend(["--ids", args.ids])
        return material_intake.main(sub_argv)

    if args.action in ("review", "apply-ruling"):
        from . import material_review

        sub_argv = [args.action, "--project-root", str(root), "--format", args.format]
        if args.volume is not None:
            sub_argv.extend(["--volume", str(args.volume)])
        sub_argv.extend(["--decay-volumes", str(args.decay_volumes)])
        for ruling in args.ruling:
            sub_argv.extend(["--ruling", ruling])
        return material_review.main(sub_argv)

    if args.action == "list":
        payload: dict[str, Any] = {}
        for table in tables or MATERIAL_TABLES:
            rows = read_table(root, table, include_archived=True)
            payload[table] = {"total": len(rows), "active": sum(1 for r in rows if r.get("状态") == "active")}
        ok = True
    elif args.action == "validate":
        problems = validate_tables(root)
        payload = {"ok": not problems, "problems": problems}
        ok = not problems
    elif args.action == "assemble":
        payload = assemble_materials(root, tables=tables, k=args.k, version=args.version)
        ok = True
    else:
        if not args.genre:
            parser.error("seed 需要 --genre")
        payload = seed_materials(root, genre=args.genre, tables=tables, source_dir=args.source_dir or None)
        ok = bool(payload["ok"])

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.action == "list":
        for table, stats in payload.items():
            print(f"{table}: {stats['total']} 条（active {stats['active']}）")
    elif args.action == "validate":
        print("OK materials" if ok else "ERROR materials")
        for problem in payload["problems"]:
            print(f"- {problem}")
    elif args.action == "assemble":
        for table, block in payload["frozen"].items():
            print(f"[定版 v{block['version']:02d}] {table}: {len(block['rows'])} 条")
        for table, rows in payload["live"].items():
            print(f"[活层 top-{payload['k']}] {table}: {len(rows)} 条")
    else:
        print(f"OK seed: +{sum(payload['seeded'].values())} 条（{payload['genre']}）；skipped={payload['skipped']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
