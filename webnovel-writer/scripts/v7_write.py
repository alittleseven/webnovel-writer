#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v7_write — v7 story-repo 写路径最小闭环（S19/E3 垂直切片）。

流程：决策卡 → 上下文包 →（LLM 草稿，工作区/）→ 机检 → 作者验收 → settle（原子 commit）。
约定跟随迁移器实际产物：定稿/正文/chNNNN.md（front matter 英文键）、
定稿/记忆/章摘要/NNNN.md（v7_cache 唯一认的摘要路径）、定稿/设定/名册/<正名>.md。
上下文包吸收 S1-S4 成果：20,000 字符总预算、section 配额、紧凑输出、缓存查询。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from data_modules.context_budget import apply_quota, estimate_tokens

PLAN_PLACEHOLDER_RE = re.compile(r"\[[^\]]*待[^\]]*\]|TODO|FIXME|\(待补\)|（待补充）")
QUOTED_NAME_RE = re.compile(r"「([一-鿿]{2,4})」")
MIN_WORDS, MAX_WORDS = 800, 6000
TOTAL_BUDGET_DEFAULT = 20000

V7_SECTION_QUOTAS: dict[str, int] = {
    "decision_card": 2000,
    "recent_summaries": 1200,
    "entities": 3000,
    "roster": 1500,
    "prev_chapter_tail": 1200,
    "book_meta": 500,
}


# ---------- 决策卡 ----------


def book_word_stats(repo: Path) -> dict[str, int]:
    """书史字数分布（从定稿正文直算，机检下限与决策卡目标字数的依据）。"""
    counts: list[int] = []
    for p in Path(repo).glob("定稿/正文/*.md"):
        text = p.read_text(encoding="utf-8")
        body = text.split("---", 2)[-1] if text.startswith("---") else text
        counts.append(len(re.sub(r"\s", "", body)))
    if not counts:
        return {"mean": 0, "median": 0, "min": 0, "max": 0, "chapters": 0}
    counts.sort()
    n = len(counts)
    return {"mean": int(sum(counts) / n), "median": counts[n // 2], "min": counts[0], "max": counts[-1], "chapters": n}


def write_decision_card(repo: Path, decision: dict[str, Any]) -> Path:
    chapter = int(decision["chapter"])
    lines = [f"# 决策卡 · 第{chapter:04d}章", ""]
    for key in ("title", "pov", "time_anchor"):
        if decision.get(key):
            lines.append(f"- {key}: {decision[key]}")
    if decision.get("target_words"):
        lines.append(f"- 目标字数: {decision['target_words']}（下限 {int(decision['target_words'] * 0.75)}）")
    lines.append(f"- 目标: {decision.get('goal', '')}")
    lines.append("- 必须覆盖节点:")
    lines += [f"  - {n}" for n in decision.get("nodes") or []]
    lines.append("- 本章禁区:")
    lines += [f"  - {n}" for n in decision.get("forbidden") or []]
    lines.append("- 承诺结转豁免: " + ("是（" + decision["waiver"] + "）" if decision.get("waiver") else "否"))
    lines.append("- 合同断言:")
    lines += [f"  - {c}" for c in decision.get("contract") or []]
    lines.append("- 关键实体: " + "、".join(decision.get("entities") or []))
    path = Path(repo) / "工作区" / f"决策卡-{chapter:04d}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------- 上下文包 ----------


def _find_setting_path(settings_dir: Path, keyword: str) -> Optional[Path]:
    exact = settings_dir / f"{keyword}.md"
    if exact.exists():
        return exact
    matches = sorted(settings_dir.glob(f"*{keyword}*.md"))
    return matches[0] if matches else None


def build_context_pack(repo: Path, decision: dict[str, Any], *, db_path: Optional[Path] = None, total_budget: int = TOTAL_BUDGET_DEFAULT):
    repo = Path(repo)
    from v7_cache import find_entity, get_summary

    chapter = int(decision["chapter"])
    sections: dict[str, Any] = {}

    card_path = repo / "工作区" / f"决策卡-{chapter:04d}.md"
    sections["decision_card"] = card_path.read_text(encoding="utf-8") if card_path.exists() else json.dumps(decision, ensure_ascii=False)

    summaries = {}
    for prev in range(max(1, chapter - 3), chapter):
        text = get_summary(repo, prev)
        if text:
            summaries[f"ch{prev:04d}"] = text[:500]
    sections["recent_summaries"] = summaries or "（暂无章摘要）"

    entities = {}
    for name in decision.get("entities") or []:
        hit = find_entity(repo, name)
        entities[name] = hit or {"name": name, "aliases": "", "first_chapter": "", "note": "名册未登记"}
    sections["entities"] = entities

    roster_files = sorted((repo / "定稿" / "设定" / "名册").glob("*.md"))
    sections["roster"] = [p.stem for p in roster_files]

    prev_chapter = chapter - 1
    prev_files = list((repo / "定稿" / "正文").glob(f"{prev_chapter:04d}-*.md"))
    if prev_files:
        text = prev_files[0].read_text(encoding="utf-8")
        sections["prev_chapter_tail"] = "……" + text[-1200:]

    book_meta = {}
    book_yaml = repo / "book.yaml"
    if book_yaml.exists():
        book_meta = {"raw": book_yaml.read_text(encoding="utf-8")[:500]}
    sections["book_meta"] = book_meta

    # S19 诊断修复：字数契约——书史基准 + 本章目标进入上下文包
    stats = book_word_stats(repo)
    target = int(decision.get("target_words") or stats["mean"] or 2000)
    sections["length_contract"] = {
        "书史章数": stats["chapters"],
        "书史均值": stats["mean"],
        "书史中位": stats["median"],
        "本章目标字数": target,
        "下限": int(target * 0.75),
    }

    stats_before = sum(estimate_tokens(v) for v in sections.values())
    for name, quota in V7_SECTION_QUOTAS.items():
        if name in sections:
            sections[name] = apply_quota(sections[name], quota)

    md = _render_pack_markdown(chapter, sections)
    used = estimate_tokens(md)
    if used > total_budget:
        md = md[: total_budget - 8] + "…（预算截断）"
        used = estimate_tokens(md)
    stats = {"used": used, "total_budget": total_budget, "sections_before": stats_before, "sections": dict(V7_SECTION_QUOTAS)}
    return md, stats


def _render_pack_markdown(chapter: int, sections: dict[str, Any]) -> str:
    out = [f"# 上下文包 · 第{chapter:04d}章", ""]
    titles = {
        "decision_card": "决策卡",
        "recent_summaries": "前情摘要（近三章，v7_cache）",
        "entities": "本章实体（名册查询）",
        "roster": "名册清单",
        "prev_chapter_tail": "上一章结尾",
        "book_meta": "书级元信息",
    }
    for name in ("decision_card", "recent_summaries", "entities", "roster", "prev_chapter_tail", "book_meta"):
        value = sections.get(name)
        if not value:
            continue
        out.append(f"## {titles.get(name, name)}")
        if isinstance(value, str):
            out.append(value)
        else:
            out.append("```json")
            out.append(json.dumps(value, ensure_ascii=False, indent=1))
            out.append("```")
        out.append("")
    return "\n".join(out)


# ---------- 机检 ----------


def run_checks(repo: Path, decision: dict[str, Any], draft_text: str) -> dict[str, Any]:
    repo = Path(repo)
    body = draft_text
    word_count = len(re.sub(r"\s", "", body))
    placeholders = sorted(set(PLAN_PLACEHOLDER_RE.findall(body)))

    title = str(decision.get("title") or "")
    first_line = next((ln.strip().lstrip("# ").strip() for ln in body.splitlines() if ln.strip()), "")
    title_ok = (not title) or (title in first_line) or (title in body[:200])

    promises = decision.get("promises") or []
    promise_ok = bool(promises) or bool(decision.get("waiver"))

    roster_names = {p.stem for p in (repo / "定稿" / "设定" / "名册").glob("*.md")}
    known = set(decision.get("entities") or []) | roster_names | set((decision.get("title") or "").split())
    new_name_candidates = sorted({n for n in QUOTED_NAME_RE.findall(body) if n not in known})

    target = int(decision.get("target_words") or 0)
    min_words = max(1, int(target * 0.75)) if target else MIN_WORDS
    ok = word_count >= min_words and not placeholders and title_ok and promise_ok
    return {
        "ok": ok,
        "word_count": word_count,
        "min_words": min_words,
        "target_words": target,
        "placeholders": placeholders,
        "title_ok": title_ok,
        "promise_ok": promise_ok,
        "new_name_candidates": new_name_candidates,
        "checks": {
            "min_words": MIN_WORDS,
            "max_words": MAX_WORDS,
            "placeholder_scan": "v7-write",
            "promise_waiver_reason": decision.get("waiver") or "",
        },
    }


# ---------- settle ----------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def settle(
    repo: Path,
    decision: dict[str, Any],
    *,
    draft_path: Path,
    summary: str,
    commit: bool = True,
) -> dict[str, Any]:
    repo = Path(repo)
    chapter = int(decision["chapter"])
    title = str(decision.get("title") or f"第{chapter}章")

    draft_text = Path(draft_path).read_text(encoding="utf-8")
    report = run_checks(repo, decision, draft_text)
    if not report["ok"]:
        raise RuntimeError(f"机检未通过，拒绝 settle：{json.dumps(report, ensure_ascii=False)}")

    # S18/E4：唯一写入路径——v6 侧已落定该章时禁止 v7 settle
    from data_modules.dual_format_guard import check_unique_write_path

    v6_root = decision.get("v6_project_root")
    if v6_root:
        blocker = check_unique_write_path(Path(v6_root), chapter, target_format="v7", story_repo_root=repo)
        if blocker:
            raise RuntimeError("唯一写入路径：" + blocker["message"])
    chapter_file = repo / "定稿" / "正文" / f"{chapter:04d}-{title}.md"
    if chapter_file.exists():
        raise RuntimeError("唯一写入路径：该章已 settle（定稿正文已存在），禁止双写")

    body = draft_text.split("---", 2)[-1].lstrip() if draft_text.startswith("---") else draft_text
    body_clean = re.sub(r"^#\s*.*?\n", "", body, count=1).lstrip()
    word_count = len(re.sub(r"\s", "", body_clean))
    front = [
        "---",
        f"章号: {chapter}",
        f"标题: {title}",
        f"卷: {decision.get('volume') or 1}",
    ]
    if decision.get("pov"):
        front.append(f"视角: {decision['pov']}")
    if decision.get("time_anchor"):
        front.append(f"书内时间: {decision['time_anchor']}")
    front.append(f"字数: {word_count}")
    if decision.get("waiver"):
        front.append(f"承诺豁免: {decision['waiver']}")
    if decision.get("promises"):
        front.append("推进承诺:")
        front += [f"  - {p}" for p in decision["promises"]]
    front.append("合同:")
    front += [f"  - {c}" for c in decision.get("contract") or []]
    front.append("---")
    chapter_file.write_text("\n".join(front) + "\n\n" + body_clean + "\n", encoding="utf-8")

    # S19 原子性：任一步失败 → 清除本次新建的定稿文件（工作区草稿原样保留）
    created: list[Path] = [chapter_file]
    try:
        summary_dir = repo / "定稿" / "记忆" / "章摘要"
        summary_dir.mkdir(parents=True, exist_ok=True)
        summary_text = (summary or "").strip()[:200]
        summary_file = summary_dir / f"{chapter:04d}.md"
        summary_file.write_text(summary_text + "\n", encoding="utf-8")
        created.append(summary_file)

        new_entities = decision.get("new_entities") or []
        for entity in new_entities:
            name = entity.get("name") or ""
            if not name:
                continue
            entity_file = repo / "定稿" / "设定" / "名册" / f"{name}.md"
            if entity_file.is_file():
                continue
            entity_file.parent.mkdir(parents=True, exist_ok=True)
            entity_file.write_text(
                "---\n"
                f"正名: {name}\n"
                f"别名: {json.dumps(entity.get('aliases') or [], ensure_ascii=False)}\n"
                f"类型: {entity.get('type') or '角色'}\n"
                f"首现章: {chapter}\n---\n",
                encoding="utf-8",
            )
            created.append(entity_file)

        result = {"chapter": chapter, "committed": False, "chapter_file": str(chapter_file), "checks": report}
        if commit:
            _git(repo, "add", "定稿")
            _git(repo, "commit", "-m", f"settle: 第{chapter:04d}章 {title}")
            result["committed"] = True
    except Exception as exc:
        for p in created:
            p.unlink(missing_ok=True)
        raise RuntimeError(f"settle 回滚：定稿未变更（{exc}）") from exc
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="v7 写路径：决策卡/上下文包/机检/settle")
    sub = parser.add_subparsers(dest="action", required=True)
    p_decision = sub.add_parser("decision", help="生成决策卡（参数经 --json 文件传入）")
    p_decision.add_argument("--repo", required=True)
    p_decision.add_argument("--json", required=True, help="决策内容 JSON 文件")
    p_pack = sub.add_parser("pack", help="生成上下文包（需已有决策卡）")
    p_pack.add_argument("--repo", required=True)
    p_pack.add_argument("--chapter", type=int, required=True)
    p_check = sub.add_parser("check", help="机检草稿")
    p_check.add_argument("--repo", required=True)
    p_check.add_argument("--chapter", type=int, required=True)
    p_check.add_argument("--draft", required=True)
    p_check.add_argument("--json", required=True, help="决策内容 JSON 文件")
    args = parser.parse_args()

    if args.action == "decision":
        decision = json.loads(Path(args.json).read_text(encoding="utf-8"))
        print(write_decision_card(Path(args.repo), decision))
        return 0
    if args.action == "pack":
        card = Path(args.repo) / "工作区" / f"决策卡-{args.chapter:04d}.md"
        decision = {"chapter": args.chapter, "title": "", "entities": []}
        md, stats = build_context_pack(Path(args.repo), decision)
        out = Path(args.repo) / "工作区" / f"上下文包-{args.chapter:04d}.md"
        out.write_text(md, encoding="utf-8")
        print(f"OK v7-write pack chapter={args.chapter} used={stats['used']:,} file={out}")
        return 0
    if args.action == "check":
        decision = json.loads(Path(args.json).read_text(encoding="utf-8"))
        report = run_checks(Path(args.repo), decision, Path(args.draft).read_text(encoding="utf-8"))
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0 if report["ok"] else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
