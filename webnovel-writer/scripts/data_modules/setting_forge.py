"""设定工坊四生成器（webnovel-copilot-300 · M4/T20，F-08，提案模式）。

流程：prepare（输入装配：设定域+素材零件+题材+author_model 雷点，0 token）→
会话内 LLM 生成 5 组概念组合提案 → save 入画廊 `设定/regen/工坊/{类}-v{N}.md`
（红线校验）→ adopt（提案扩写为设定文档草案，仍走画廊二次确认）→
confirm（登记三处同步：设定域 md + 力量锚点同步标记（涉战力类）+ 合同重编译标记，
并写采纳率信号 `演化/signals.jsonl`）。

红线（save 时程序化强制）：
- 不生成战力数值——提案文本含 `战力/攻击力/防御力...: 数字` 即拒绝；
- 核心金手指/主角独特性类（境界/功法）必须标注
  「灵魂设定——建议作者自拟，工坊仅给反差参考」；
- 一批必须恰 5 组提案（`## 提案 N` 小节）。
交互红线：LLM 只提议、作者只确认；confirm 不改作者手写设定文件，只落登记草案。
"""

from __future__ import annotations

import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .author_journal import append_events
from .author_model import read_preferences

FORGE_SCHEMA_VERSION = "setting-forge/1"
GALLERY_REL = Path("设定") / "regen" / "工坊"
FORGE_CATEGORIES = ("境界", "功法", "法宝", "命名")
PROPOSAL_COUNT = 5
SOUL_ANNOTATION = "灵魂设定——建议作者自拟，工坊仅给反差参考"
SOUL_CATEGORIES = ("境界", "功法")  # 核心/主角独特性类
_NUMERIC_POWER_RE = re.compile(r"(战力值?|攻击力|防御力|破坏力|数值)\s*[:：=]?\s*\d+", re.IGNORECASE)
_PROPOSAL_RE = re.compile(r"^##\s*提案\s*\d+", re.MULTILINE)
_SETTINGS_DIRS = ("定稿/设定", "设定集")


def gallery_dir(project_root: str | Path) -> Path:
    return Path(project_root) / GALLERY_REL


def _settings_dir(project_root: Path) -> Path:
    for rel in _SETTINGS_DIRS:
        candidate = project_root / rel
        if candidate.is_dir():
            return candidate
    return project_root / _SETTINGS_DIRS[0]


def forge_prepare(project_root: str | Path, *, category: str) -> dict[str, Any]:
    """F-08 步骤①：输入装配简报（0 token）。素材零件/雷点/红线提示齐备供会话生成。"""
    if category not in FORGE_CATEGORIES:
        return {"ok": False, "error": "invalid_category", "allowed": list(FORGE_CATEGORIES)}
    root = Path(project_root)
    parts: list[str] = [f"# 工坊输入装配 · {category}", ""]

    part_rows: list[dict[str, str]] = []
    from .material_store import read_table

    for table in ("金手指零件", "世界观零件"):
        part_rows.extend(read_table(root, table)[:5])
    if part_rows:
        parts.append("## 素材零件（活层 top 摘录）")
        for row in part_rows:
            parts.append(f"- [{row.get('id')}] {row.get('名称')}：{row.get('核心摘要', '')[:40]}")
        parts.append("")

    prefs = read_preferences(root)
    taboos = prefs.get("雷点") or []
    parts.append("## author_model 雷点（提案必须避开）")
    if taboos:
        parts.extend(f"- {t}" for t in taboos)
    else:
        parts.append("- （无登记）")
    parts.append("")

    parts.append(
        f"## 红线\n- {SOUL_ANNOTATION}（{'、'.join(SOUL_CATEGORIES)}类必标）\n- 不生成战力数值\n- 一批恰 {PROPOSAL_COUNT} 组概念组合提案（非成品）"
    )

    template = "\n".join(
        [f"# {category}提案（5 组概念组合）", ""]
        + [line for i in range(1, PROPOSAL_COUNT + 1) for line in (
            f"## 提案 {i}", "- 概念拼接：", "- 反差钩子：", "- 差异点：", "- 常见度自评：", "")]
        + ["", SOUL_ANNOTATION]
    )
    brief = "\n".join(parts)
    return {"ok": True, "category": category, "brief": brief, "template": template, "schema_version": FORGE_SCHEMA_VERSION}


def list_versions(project_root: str | Path, *, category: str) -> list[dict[str, Any]]:
    gallery = gallery_dir(project_root)
    if not gallery.is_dir():
        return []
    versions: list[dict[str, Any]] = []
    for file in sorted(gallery.glob(f"{category}-v*.md")):
        match = re.fullmatch(rf"{category}-v(\d+)\.md", file.name)
        if match:
            text = file.read_text(encoding="utf-8")
            versions.append({"version": int(match.group(1)), "file": file.name, "proposals": len(_PROPOSAL_RE.findall(text))})
    return versions


def _validate_proposals(text: str, category: str) -> dict[str, Any] | None:
    """红线校验；通过返回 None，否则返回错误报告。"""
    count = len(_PROPOSAL_RE.findall(text))
    if count != PROPOSAL_COUNT:
        return {"ok": False, "error": "proposal_count", "count": count, "expected": PROPOSAL_COUNT}
    hit = _NUMERIC_POWER_RE.search(text)
    if hit:
        return {"ok": False, "error": "numeric_power_detected", "hit": hit.group(0)}
    if category in SOUL_CATEGORIES and SOUL_ANNOTATION not in text:
        return {"ok": False, "error": "soul_annotation_missing", "annotation": SOUL_ANNOTATION}
    return None


def forge_save(project_root: str | Path, *, category: str, file: str | Path) -> dict[str, Any]:
    """F-08 步骤③：提案入画廊（红线校验通过才写）。留 journal(regen, 设定)。"""
    if category not in FORGE_CATEGORIES:
        return {"ok": False, "error": "invalid_category", "allowed": list(FORGE_CATEGORIES)}
    source = Path(file)
    if not source.is_file():
        return {"ok": False, "error": "file_missing", "file": str(source)}
    text = source.read_text(encoding="utf-8")
    violation = _validate_proposals(text, category)
    if violation is not None:
        return violation

    root = Path(project_root)
    gallery = gallery_dir(root)
    gallery.mkdir(parents=True, exist_ok=True)
    existing = [int(m.group(1)) for f in gallery.glob(f"{category}-v*.md") if (m := re.fullmatch(rf"{category}-v(\d+)\.md", f.name))]
    version = max(existing, default=0) + 1
    target = gallery / f"{category}-v{version}.md"
    target.write_text(text, encoding="utf-8", newline="\n")
    append_events(
        root,
        [
            {
                "actor": "ai",
                "action": "regen",
                "domain": "设定",
                "path": f"{GALLERY_REL.as_posix()}/{target.name}",
                "change_kind": "add",
                "diff_stat": {"ins": PROPOSAL_COUNT, "del": 0},
                "summary": f"工坊提案入画廊：{category} v{version}（{PROPOSAL_COUNT} 组）",
                "impact": [],
            }
        ],
    )
    return {"ok": True, "schema_version": FORGE_SCHEMA_VERSION, "category": category, "version": version, "file": str(target)}


def forge_adopt(project_root: str | Path, *, category: str, version: int, proposal: int) -> dict[str, Any]:
    """F-08 步骤④前半：采纳提案 → 扩写为设定文档草案（仍走画廊二次确认）。"""
    gallery = gallery_dir(project_root)
    source = gallery / f"{category}-v{int(version)}.md"
    if not source.is_file():
        return {"ok": False, "error": "version_missing", "file": source.name}
    text = source.read_text(encoding="utf-8")
    sections = _PROPOSAL_RE.split(text)
    # sections[0] 为标题前导；提案 K 对应 sections[K]
    if proposal < 1 or proposal >= len(sections):
        return {"ok": False, "error": "proposal_missing", "proposal": proposal}
    chosen = sections[int(proposal)].strip()

    root = Path(project_root)
    draft = gallery / f"{category}-v{int(version)}-提案{int(proposal)}-草案.md"
    draft.write_text(
        f"# {category}设定草案（工坊提案 {int(version)}-{int(proposal)} 扩写，待作者二次确认）\n\n"
        f"{chosen}\n\n---\n登记状态：草案（forge confirm 后三处同步）\n",
        encoding="utf-8",
        newline="\n",
    )
    return {"ok": True, "schema_version": FORGE_SCHEMA_VERSION, "category": category, "draft": str(draft)}


def forge_confirm(project_root: str | Path, *, category: str, draft: str | Path) -> dict[str, Any]:
    """F-08 步骤④后半：作者二次确认 → 登记三处同步 + 采纳率信号。

    ①设定域：草案复制为 `设定域/工坊-{类}-草案名.md`；
    ②力量锚点：涉战力类（境界/功法）登记 `power_anchor_sync: required`（锚点表本身
      作者所有，实际同步由作者按锚点流程确认，不自动改写）；
    ③合同重编译：登记 `contract_rebuild: required`（编译产物由 master-outline-sync 链处理）。
    """
    root = Path(project_root)
    source = Path(draft)
    if not source.is_file():
        return {"ok": False, "error": "draft_missing", "draft": str(source)}
    settings_dir = _settings_dir(root)
    settings_dir.mkdir(parents=True, exist_ok=True)
    registered = settings_dir / f"工坊-{source.stem}.md"
    shutil.copy2(source, registered)

    anchor_sync = "required" if category in SOUL_CATEGORIES else "not_applicable"
    impact = ["contract_rebuild:required"]
    if anchor_sync == "required":
        impact.append("power_anchor_sync:required")

    append_events(
        root,
        [
            {
                "actor": "author",
                "action": "adopt",
                "domain": "设定",
                "path": registered.relative_to(root).as_posix(),
                "change_kind": "add",
                "diff_stat": {"ins": 1, "del": 0},
                "summary": f"工坊采纳登记：{category}（{source.name}）三处同步",
                "impact": impact,
            }
        ],
    )

    signals = root / "演化" / "signals.jsonl"
    signals.parent.mkdir(parents=True, exist_ok=True)
    with signals.open("a", encoding="utf-8", newline="\n") as file:
        file.write(
            json.dumps(
                {
                    "type": "forge_adopt",
                    "ts": time.time(),
                    "time": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                    "category": category,
                    "adopted": True,
                    "proposed_count": PROPOSAL_COUNT,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return {
        "ok": True,
        "schema_version": FORGE_SCHEMA_VERSION,
        "registered": str(registered),
        "anchor_sync": anchor_sync,
        "contract_rebuild": "required",
    }


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python -X utf8 setting_forge.py {prepare|save|adopt|confirm|list} [options]

    一般经 `webnovel.py forge <action>` 调用（F-08：/webnovel:forge [境界|功法|法宝|命名]）。
    """
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="设定工坊四生成器（T20，提案模式）")
    parser.add_argument("action", choices=["prepare", "save", "adopt", "confirm", "list"])
    parser.add_argument("--category", default="", help=f"境界/功法/法宝/命名 之一（{'/'.join(FORGE_CATEGORIES)}）")
    parser.add_argument("--file", default="", help="save：提案 md 文件")
    parser.add_argument("--version", type=int, default=None, help="adopt：画廊版本")
    parser.add_argument("--proposal", type=int, default=None, help="adopt：提案编号（1-5）")
    parser.add_argument("--draft", default="", help="confirm：草案文件")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    if args.action == "prepare":
        report = forge_prepare(root, category=args.category)
    elif args.action == "save":
        if not args.category or not args.file:
            parser.error("save 需要 --category 与 --file")
        report = forge_save(root, category=args.category, file=args.file)
    elif args.action == "adopt":
        if not args.category or args.version is None or args.proposal is None:
            parser.error("adopt 需要 --category --version --proposal")
        report = forge_adopt(root, category=args.category, version=args.version, proposal=args.proposal)
    elif args.action == "confirm":
        if not args.category or not args.draft:
            parser.error("confirm 需要 --category 与 --draft")
        report = forge_confirm(root, category=args.category, draft=args.draft)
    else:
        report = {"ok": True, "versions": list_versions(root, category=args.category)} if args.category else {"ok": False, "error": "invalid_category"}

    if args.format == "json":
        print(_json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok", True) else 1

    if args.action == "prepare":
        if not report.get("ok"):
            print(f"ERROR {report.get('error')}")
            return 1
        print(report["brief"])
        print("--- 提案模板 ---")
        print(report["template"])
    elif args.action == "list":
        for item in report["versions"]:
            print(f"{item['file']}  {item['proposals']} 组提案")
        if not report["versions"]:
            print("(画廊为空)")
    else:
        if not report.get("ok"):
            print(f"ERROR {report.get('error')}" + (f"（{report.get('hit', '')}）" if report.get("hit") else ""))
            return 1
        if args.action == "save":
            print(f"OK 入画廊 {report['category']}-v{report['version']}")
        elif args.action == "adopt":
            print(f"OK 草案：{Path(report['draft']).name}")
        else:
            print(f"OK 已登记 {report['registered']}；锚点同步={report['anchor_sync']}；合同重编译={report['contract_rebuild']}")
    return 0 if report.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
