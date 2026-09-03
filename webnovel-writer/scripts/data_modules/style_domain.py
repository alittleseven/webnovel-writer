"""文风域数据面（webnovel-copilot-300 · M3/T15，05 §1 / 06 §6 / F-05 / F-12）。

三个资产：
- `文风/宪法.md`：文风契约，由既有 `风格契约.md` 经 `migrate_constitution` 平移迁入
  （迁移=原位置退役；既有宪法一律不覆盖，作者主权 P1/P2）。
- `文风/金句库.md`：作者标记的高分片段（G-NNN 编号），是台词金句素材表的自喂入口
  （`feed_golden` → `素材/活/台词金句.csv`，来源=作者手写）。
- `文风/指纹.yaml`：style_profile（06 §6 全字段），由定稿正文统计——脚本可算、
  纯确定性（同一定稿两次计算逐字段一致）；settle 后增量更新（T17 接线）。

红线：不改动正文与作者手写文件；YAML 用内置最小读写器（仓库零第三方依赖约定）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .author_journal import append_events
from .material_store import append_entries

STYLE_SCHEMA_VERSION = "style-profile/1"
CONSTITUTION_REL = Path("文风") / "宪法.md"
GOLDEN_REL = Path("文风") / "金句库.md"
FINGERPRINT_REL = Path("文风") / "指纹.yaml"
_CONSTITUTION_SOURCES = ("设定集/风格契约.md", "定稿/设定/风格契约.md")
CHAPTER_DIR = Path("定稿") / "正文"
PARAGRAPH_CAP = 300

# said-tag 判定的口播动词（正文中「X说/X道」类对白引导语）
_SAID_VERBS = ("说", "道", "问", "答", "喊", "叫", "骂", "念", "嘀咕", "吩咐", "回答", "嚷", "嘀咕")
_DIALOGUE_RE = re.compile(r"「([^」]*)」|“([^”]*)”")
_SENT_SPLIT_RE = re.compile(r"[。！？!?]+")
_PUNCT_STRIP_RE = re.compile(r"[，。！？!?：:；;、「」“”\s—…·\n\r]")
# 二字口头禅统计时排除的常用虚词组合（单字虚词集合，双字含任一即排除）
_STOPWORD_CHARS = set("的了是在不在有着就和但也都很之乎者把被而为这那又再才只更还会要能可是就")


# ---------------------------------------------------------------------------
# 宪法迁移（05 §3：设定集/风格契约.md → 文风/宪法.md）
# ---------------------------------------------------------------------------

def constitution_path(project_root: str | Path) -> Path:
    return Path(project_root) / CONSTITUTION_REL


def migrate_constitution(project_root: str | Path) -> dict[str, Any]:
    """平移 风格契约.md → 文风/宪法.md（移动语义：原位置退役）。既有宪法不覆盖。"""
    root = Path(project_root)
    target = constitution_path(root)
    if target.is_file():
        return {"ok": True, "migrated": False, "reason": "constitution_exists", "target": str(target)}

    source: Path | None = None
    for rel in _CONSTITUTION_SOURCES:
        candidate = root / rel
        if candidate.is_file():
            source = candidate
            break
    if source is None:
        matches = [p for p in root.glob(f"**/{'风格契约'}.md") if ".git" not in p.parts and p != target]
        source = matches[0] if matches else None
    if source is None:
        return {"ok": True, "migrated": False, "reason": "no_source"}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    source.unlink()
    append_events(
        root,
        [
            {
                "actor": "system",
                "action": "edit",
                "domain": "文风",
                "path": CONSTITUTION_REL.as_posix(),
                "change_kind": "structure",
                "diff_stat": {"ins": 1, "del": 0},
                "summary": f"文风宪法迁移：{source.relative_to(root).as_posix()} → {CONSTITUTION_REL.as_posix()}",
                "impact": [],
            }
        ],
    )
    return {"ok": True, "migrated": True, "source": str(source), "target": str(target)}


# ---------------------------------------------------------------------------
# 金句库（素材自喂入口）
# ---------------------------------------------------------------------------

def golden_path(project_root: str | Path) -> Path:
    return Path(project_root) / GOLDEN_REL


def list_goldens(project_root: str | Path) -> list[dict[str, Any]]:
    path = golden_path(project_root)
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    entries: list[dict[str, Any]] = []
    for match in re.finditer(
        r"^## (G-\d+) · 第(\d+)章\n> (.+?)(?:\n备注: (.*))?$",
        text,
        re.MULTILINE,
    ):
        entries.append(
            {
                "id": match.group(1),
                "章": int(match.group(2)),
                "摘录": match.group(3).strip(),
                "备注": (match.group(4) or "").strip(),
            }
        )
    return entries


def add_golden(project_root: str | Path, *, chapter: int, text: str, note: str = "") -> dict[str, Any]:
    """作者标记高分片段入金句库（G-NNN 顺序编号）。留 journal(learn, 文风)。"""
    text = str(text or "").strip()
    if not text:
        return {"ok": False, "error": "empty_text"}
    entries = list_goldens(project_root)
    next_seq = max((int(e["id"].split("-")[1]) for e in entries), default=0) + 1
    golden_id = f"G-{next_seq:03d}"
    path = golden_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text("# 金句库（作者标记的高分片段）\n\n", encoding="utf-8", newline="\n")
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(f"## {golden_id} · 第{int(chapter)}章\n")
        file.write(f"> {text}\n")
        if note:
            file.write(f"备注: {note}\n")
        file.write("\n")
    append_events(
        project_root,
        [
            {
                "actor": "author",
                "action": "learn",
                "domain": "文风",
                "path": GOLDEN_REL.as_posix(),
                "change_kind": "add",
                "diff_stat": {"ins": 1, "del": 0},
                "summary": f"标记金句 {golden_id}（第{int(chapter)}章）",
                "impact": [],
            }
        ],
    )
    return {"ok": True, "id": golden_id, "schema_version": STYLE_SCHEMA_VERSION}


def feed_golden(project_root: str | Path, *, golden_id: str) -> dict[str, Any]:
    """金句 → 台词金句素材表（自喂入口，来源=作者手写）。重复投喂按 duplicate_id 拒绝。"""
    entry = next((e for e in list_goldens(project_root) if e["id"] == golden_id), None)
    if entry is None:
        return {"ok": False, "error": "golden_missing", "id": golden_id}
    report = append_entries(
        project_root,
        "台词金句",
        [
            {
                "id": golden_id,
                "名称": entry["摘录"],
                "分类": "金句",
                "核心摘要": entry["摘录"][:50],
                "备注": f"自喂自第{entry['章']}章金句库",
            }
        ],
        source="作者手写",
        journal_summary=f"金句 {golden_id} 自喂入台词金句表",
    )
    return report if not report.get("ok") else {**report, "golden": entry}


# ---------------------------------------------------------------------------
# 指纹计算器（06 §6 style_profile，纯确定性）
# ---------------------------------------------------------------------------

def fingerprint_path(project_root: str | Path) -> Path:
    return Path(project_root) / FINGERPRINT_REL


def _chapter_bodies(project_root: Path, chapters: list[int] | None = None) -> list[tuple[int, str]]:
    root = Path(project_root)
    chapter_dir = root / CHAPTER_DIR
    if not chapter_dir.is_dir():
        return []
    wanted = set(chapters or [])
    bodies: list[tuple[int, str]] = []
    for path in sorted(chapter_dir.glob("*.md")):
        match = re.match(r"(\d{4})", path.stem)
        if not match:
            continue
        chapter = int(match.group(1))
        if wanted and chapter not in wanted:
            continue
        text = path.read_text(encoding="utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) == 3:
                text = parts[2]
        bodies.append((chapter, text.strip()))
    return sorted(bodies, key=lambda pair: pair[0])


def _compute_fingerprint(bodies: list[tuple[int, str]], goldens: list[dict[str, Any]]) -> dict[str, Any]:
    total_text = "\n".join(body for _, body in bodies)
    chapter_count = len(bodies)
    total_chars = len(_PUNCT_STRIP_RE.sub("", total_text))

    sentences = [s.strip() for s in _SENT_SPLIT_RE.split(total_text) if s.strip()]
    lengths = [len(_PUNCT_STRIP_RE.sub("", s)) for s in sentences] or [0]
    mean_len = sum(lengths) / len(lengths)
    variance = sum((x - mean_len) ** 2 for x in lengths) / len(lengths)
    sorted_len = sorted(lengths)
    p90 = float(sorted_len[min(len(sorted_len) - 1, int(0.9 * (len(sorted_len) - 1)))])

    paragraphs = [ln.strip() for ln in total_text.splitlines() if ln.strip()]
    para_lengths = [len(ln) for ln in paragraphs]
    mean_para = (sum(para_lengths) / len(para_lengths)) if para_lengths else 0.0
    cap_hits = (sum(1 for ln in para_lengths if ln > PARAGRAPH_CAP) / len(para_lengths)) if para_lengths else 0.0

    dialogues = [m.group(0) for m in _DIALOGUE_RE.finditer(total_text)]
    dialogue_chars = sum(len(m) for m in dialogues)
    dialogue_ratio = (dialogue_chars / len(total_text)) if total_text else 0.0
    tagged = 0
    for match in _DIALOGUE_RE.finditer(total_text):
        before = total_text[max(0, match.start() - 12): match.start()]
        after = total_text[match.end(): match.end() + 6]
        if any(verb in before or verb in after for verb in _SAID_VERBS):
            tagged += 1
    said_ratio = (tagged / len(dialogues)) if dialogues else 0.0

    cleaned = _PUNCT_STRIP_RE.sub("", total_text)
    grams: dict[str, int] = {}
    for index in range(len(cleaned) - 1):
        gram = cleaned[index: index + 2]
        if gram[0] in _STOPWORD_CHARS or gram[1] in _STOPWORD_CHARS:
            continue
        grams[gram] = grams.get(gram, 0) + 1
    top_grams = sorted(grams.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    catchphrases = [
        {"词": gram, "每章频次": round(count / chapter_count, 1) if chapter_count else 0.0}
        for gram, count in top_grams
    ]

    dash_rate = (total_text.count("——") / total_chars * 1000) if total_chars else 0.0
    ellipsis_rate = (total_text.count("……") / total_chars * 1000) if total_chars else 0.0

    return {
        "schema_version": STYLE_SCHEMA_VERSION,
        "定稿章数": chapter_count,
        "句长": {"均值": round(mean_len, 1), "p90": round(p90, 1), "方差": round(variance, 1)},
        "段落": {"均值字数": round(mean_para, 1), "单段上限命中率": round(cap_hits, 2)},
        "对话占比": round(dialogue_ratio, 2),
        "said_tag_ratio": round(said_ratio, 2),
        "高频口头禅": catchphrases,
        "标点": {"破折号率": round(dash_rate, 1), "省略号率": round(ellipsis_rate, 1)},
        "金句样本": [{"章": g["章"], "摘录": g["摘录"]} for g in goldens],
    }


def read_fingerprint(project_root: str | Path) -> dict[str, Any]:
    """解析 指纹.yaml（内置最小读取器，只认本模块发射的固定 schema）。"""
    path = fingerprint_path(project_root)
    if not path.is_file():
        return {}
    result: dict[str, Any] = {}
    section: str | None = None
    current_item: dict[str, Any] | None = None
    list_sections = {"高频口头禅", "金句样本"}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0:
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip()
            if value == "":
                section = key
                current_item = None
                result[key] = {} if key not in list_sections else []
            else:
                result[key] = _parse_scalar(value)
                section = None
        elif line.startswith("- ") and section in list_sections:
            current_item = {}
            key, _, value = line[2:].partition(":")
            current_item[key.strip()] = _parse_scalar(value.strip())
            result[section].append(current_item)
        elif section in list_sections and current_item is not None:
            key, _, value = line.partition(":")
            current_item[key.strip()] = _parse_scalar(value.strip())
        elif section is not None:
            key, _, value = line.partition(":")
            result[section][key.strip()] = _parse_scalar(value.strip())
    return result


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def write_fingerprint(project_root: str | Path, fingerprint: dict[str, Any]) -> Path:
    """发射固定 schema 的指纹 YAML（最小写入器；内容确定性，无时间戳字段）。"""
    path = fingerprint_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        f"schema_version: {fingerprint.get('schema_version', STYLE_SCHEMA_VERSION)}",
        f"定稿章数: {fingerprint.get('定稿章数', 0)}",
    ]
    for section in ("句长", "段落", "标点"):
        lines.append(f"{section}:")
        for key, value in (fingerprint.get(section) or {}).items():
            lines.append(f"  {key}: {_emit_scalar(value)}")
    lines.append(f"对话占比: {_emit_scalar(fingerprint.get('对话占比', 0.0))}")
    lines.append(f"said_tag_ratio: {_emit_scalar(fingerprint.get('said_tag_ratio', 0.0))}")
    for section, key_order in (("高频口头禅", ("词", "每章频次")), ("金句样本", ("章", "摘录"))):
        lines.append(f"{section}:")
        for item in fingerprint.get(section) or []:
            first_key = key_order[0]
            rest = [k for k in key_order if k != first_key]
            lines.append(f"  - {first_key}: {_emit_scalar(item.get(first_key))}")
            for key in rest:
                lines.append(f"    {key}: {_emit_scalar(item.get(key))}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _emit_scalar(value: Any) -> str:
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, float) and value.is_integer():
        return f"{value:.1f}"
    return str(value)


def write_fingerprint_from_book(
    project_root: str | Path,
    *,
    chapters: list[int] | None = None,
) -> dict[str, Any]:
    """从定稿正文全量计算并写入指纹（确定性；指定 chapters 时为单章增量口径）。"""
    root = Path(project_root)
    bodies = _chapter_bodies(root, chapters)
    fingerprint = _compute_fingerprint(bodies, list_goldens(root))
    write_fingerprint(root, fingerprint)
    return {"ok": True, "schema_version": STYLE_SCHEMA_VERSION, "chapters": fingerprint["定稿章数"]}


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python -X utf8 style_domain.py {migrate|fingerprint|golden-add|golden-list|golden-feed}"""
    import argparse

    parser = argparse.ArgumentParser(description="文风域数据面（T15）")
    parser.add_argument("action", choices=["migrate", "fingerprint", "golden-add", "golden-list", "golden-feed"])
    parser.add_argument("--chapter", type=int, default=None)
    parser.add_argument("--text", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--id", default="", help="golden-feed 的金句编号")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    if args.action == "migrate":
        report = migrate_constitution(root)
    elif args.action == "fingerprint":
        chapters = [args.chapter] if args.chapter else None
        report = write_fingerprint_from_book(root, chapters=chapters)
    elif args.action == "golden-add":
        if not args.text or args.chapter is None:
            parser.error("golden-add 需要 --chapter 与 --text")
        report = add_golden(root, chapter=args.chapter, text=args.text, note=args.note)
    elif args.action == "golden-list":
        report = {"ok": True, "goldens": list_goldens(root)}
    else:
        if not args.id:
            parser.error("golden-feed 需要 --id")
        report = feed_golden(root, golden_id=args.id)

    if args.format == "json":
        import json as _json

        print(_json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok", True) else 1

    if args.action == "migrate":
        if report.get("migrated"):
            print(f"OK 宪法迁移：{report['source']} → {report['target']}")
        else:
            print(f"SKIP {report.get('reason')}（宪法未变更）")
    elif args.action == "fingerprint":
        print(f"OK 指纹已写入（{report['chapters']} 章口径）→ {fingerprint_path(root)}")
    elif args.action == "golden-add":
        print(f"OK 金句 {report['id']} 已标记")
    elif args.action == "golden-list":
        for entry in report["goldens"]:
            note = f"（{entry['备注']}）" if entry["备注"] else ""
            print(f"{entry['id']}  第{entry['章']}章  {entry['摘录']}{note}")
        if not report["goldens"]:
            print("(金句库为空)")
    else:
        print(f"OK 金句 {args.id} 已自喂入台词金句表")
    return 0 if report.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
