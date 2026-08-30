#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""migrate_v6_to_v7 — v6 书项目 → v7 story-repo 只读迁移（S16/E1）。

目标格式：docs/architecture/story-repo-spec-2026-06-10.md（spec 0.4，spec_version "7.0"）。
原则：对 v6 源零写入；输出目录已存在则拒绝；内容无损迁移，仅在正文前追加 front matter；
无法结构化的部分（承诺/审查报告/增强设定）明确列入报告的 skipped，不静默丢弃。

用法：
    python -X utf8 migrate_v6_to_v7.py --project-root <v6根> --output <新v7目录> [--no-git]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MigrationReport:
    chapters: int = 0
    summaries: int = 0
    settings: int = 0
    outlines: int = 0
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    output: str = ""

    def as_lines(self) -> list[str]:
        return [
            f"OK migrate v6->v7 输出={self.output}",
            f"chapters={self.chapters} summaries={self.summaries} settings={self.settings} outlines={self.outlines}",
            f"warnings={len(self.warnings)} skipped={len(self.skipped)}",
            *[f"  WARN {w}" for w in self.warnings],
            *[f"  SKIP {s}" for s in self.skipped],
        ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _quote_yaml(value: str) -> str:
    """防呆方言：可能被 YAML 误判类型的值加引号。"""
    if re.fullmatch(r"-?\d+(\.\d+)?|true|false|yes|no|是|否|null|~", value, re.IGNORECASE):
        return f'"{value}"'
    return value


def _load_state(project_root: Path) -> dict:
    state_file = project_root / ".webnovel" / "state.json"
    if not state_file.exists():
        return {}
    try:
        return json.loads(_read(state_file))
    except (json.JSONDecodeError, OSError):
        return {}


def _volume_map(project_root: Path) -> dict[int, int]:
    """从 大纲/第N卷-时间线.md 的「第M章」行解析 章节→卷 映射；解析不到默认卷 1。"""
    mapping: dict[int, int] = {}
    for tl in sorted(project_root.glob("大纲/第*卷-时间线.md")):
        m = re.search(r"第(\d+)卷", tl.name)
        if not m:
            continue
        vol = int(m.group(1))
        for line in _read(tl).splitlines():
            cm = re.search(r"第(\d+)章", line)
            if cm:
                mapping.setdefault(int(cm.group(1)), vol)
    return mapping


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(_read(src), encoding="utf-8")


def _migrate_chapters(project_root: Path, out: Path, vols: dict[int, int], report: MigrationReport) -> None:
    body_dir = project_root / "正文"
    target = out / "定稿" / "正文"
    target.mkdir(parents=True, exist_ok=True)
    for src in sorted(body_dir.glob("第*.md")):
        m = re.match(r"第(\d+)章[-—]?(.*)\.md", src.name)
        if not m:
            report.skipped.append(f"正文/{src.name}（文件名无法解析章号）")
            continue
        chapter = int(m.group(1))
        title = m.group(2).strip() or f"第{chapter}章"
        content = _read(src)
        word_count = len(re.sub(r"\s", "", content))
        front = (
            "---\n"
            f"章号: {chapter}\n"
            f"标题: {title}\n"
            f"卷: {vols.get(chapter, 1)}\n"
            f"字数: {word_count}\n"
            f"迁移来源: v6/{src.name}\n"
            "---\n"
        )
        (target / f"{chapter:04d}-{title}.md").write_text(front + content, encoding="utf-8")
        report.chapters += 1


def _migrate_settings(project_root: Path, out: Path, state: dict, report: MigrationReport) -> None:
    settings = project_root / "设定集"
    target = out / "定稿" / "设定"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("世界观", "力量体系", "反派设计"):
        src = settings / f"{name}.md"
        if src.exists():
            _copy(src, target / f"{name}.md")
            report.settings += 1

    protagonist_name = str(((state.get("protagonist_state") or {}).get("name")) or "").strip()
    for card, target_name in (
        ("主角卡.md", f"{protagonist_name}.md" if protagonist_name else "主角卡.md"),
        ("女主卡.md", "女主卡.md"),
        ("配角卡.md", "配角卡.md"),
    ):
        src = settings / card
        if src.exists():
            _copy(src, target / "角色" / target_name)
            report.settings += 1
            if card == "主角卡.md" and not protagonist_name:
                report.warnings.append("state 缺 protagonist_state.name，主角卡保留原文件名")

    for extra in sorted(settings.glob("*.md")):
        if extra.stem in {"世界观", "力量体系", "反派设计", "主角卡", "女主卡", "配角卡", "风格契约"}:
            continue
        _copy(extra, target / f"{extra.stem}.md")
        report.settings += 1

    # 时间线：合并为 append-only 表（多卷按卷号顺序拼接）
    timelines = sorted(project_root.glob("大纲/第*卷-时间线.md"))
    if timelines:
        parts = ["# 时间线\n"]
        for tl in timelines:
            parts.append(f"\n## {tl.stem}\n\n" + _read(tl).strip() + "\n")
        (target / "时间线.md").write_text("\n".join(parts), encoding="utf-8")
        report.settings += 1

    # 名册：从 index.db 实体表生成（库缺失则跳过）
    index_db = project_root / ".webnovel" / "index.db"
    if index_db.exists():
        try:
            import sqlite3

            conn = sqlite3.connect(index_db)
            try:
                rows = conn.execute(
                    "SELECT e.canonical_name, e.first_appearance, GROUP_CONCAT(a.alias, ', ')"
                    " FROM entities e LEFT JOIN aliases a ON a.entity_id = e.id"
                    " WHERE e.is_archived = 0"
                    " GROUP BY e.id ORDER BY e.first_appearance, e.canonical_name"
                ).fetchall()
            finally:
                conn.close()
            lines = ["# 实体名册\n", "| 正名 | 别名 | 首现章 |", "|---|---|---|"]
            for name, first, aliases in rows:
                lines.append(f"| {name} | {aliases or ''} | {first or ''} |")
            (target / "名册.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
            report.settings += 1
        except (sqlite3.Error, OSError) as exc:
            report.warnings.append(f"名册生成失败（index.db 不可读）：{exc}")


def _migrate_summaries(project_root: Path, out: Path, report: MigrationReport) -> None:
    summaries = project_root / ".webnovel" / "summaries"
    if not summaries.exists():
        return
    target = out / "定稿" / "记忆" / "章摘要"
    target.mkdir(parents=True, exist_ok=True)
    for src in sorted(summaries.glob("ch*.md")):
        m = re.match(r"ch(\d+)\.md", src.name)
        if not m:
            continue
        _copy(src, target / f"{int(m.group(1)):04d}.md")
        report.summaries += 1


def _migrate_outlines(project_root: Path, out: Path, report: MigrationReport) -> None:
    outline = project_root / "大纲"
    target = out / "大纲"
    target.mkdir(parents=True, exist_ok=True)
    total = outline / "总纲.md"
    if total.exists():
        _copy(total, target / "总纲.md")
        report.outlines += 1
    for detail in sorted(outline.glob("第*卷-详细大纲.md")):
        vol = re.search(r"第(\d+)卷", detail.name)
        stem = f"第{int(vol.group(1)):02d}卷" if vol else detail.stem
        _copy(detail, target / "卷纲" / f"{stem}.md")
        report.outlines += 1
    for beats in sorted(outline.glob("第*卷-节拍表.md")):
        vol = re.search(r"第(\d+)卷", beats.name)
        stem = f"第{int(vol.group(1)):02d}卷" if vol else beats.stem
        _copy(beats, target / "卷纲" / f"{stem}-节拍表.md")
        report.outlines += 1


def _write_book_yaml(out: Path, state: dict) -> None:
    info = state.get("project_info") or {}
    lines = [
        'spec_version: "7.0"',
        f"书名: {_quote_yaml(str(info.get('title') or '未命名'))}",
        f"类型: {_quote_yaml(str(info.get('genre') or '都市'))}",
    ]
    if info.get("genre_label"):
        lines.append(f"题材标签: {_quote_yaml(str(info['genre_label']))}")
    if info.get("target_words") and info.get("target_chapters"):
        per_chapter = int(int(info["target_words"]) / max(1, int(info["target_chapters"])))
        lines.append(f"每章目标字数: {per_chapter}")
        lines.append(f"卷规模: 40")
    lines.append("高承诺最大搁置章数: 10")
    lines.append("连续弱钩上限: 3")
    (out / "book.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _git_init(out: Path, chapters: int) -> None:
    def run(*args: str) -> None:
        subprocess.run(args, cwd=out, check=True, capture_output=True, text=True, encoding="utf-8")

    run("git", "init")
    run("git", "config", "core.quotepath", "false")
    run("git", "add", "-A")
    run("git", "-c", "user.name=webnovel-migrator", "-c", "user.email=migrator@local",
        "commit", "-m", f"ch: v6 迁移导入（{chapters} 章）")


def migrate_project(project_root: str | Path, output: str | Path, *, use_git: bool = True) -> MigrationReport:
    project_root = Path(project_root).resolve()
    out = Path(output).resolve()
    if out.exists():
        raise FileExistsError(f"输出目录已存在，拒绝覆盖：{out}")
    if not (project_root / ".webnovel" / "state.json").exists() and not (project_root / "正文").exists():
        raise NotADirectoryError(f"不是 v6 书项目（缺 .webnovel/state.json 与 正文/）：{project_root}")

    report = MigrationReport(output=str(out))
    state = _load_state(project_root)
    vols = _volume_map(project_root)

    out.mkdir(parents=True)
    (out / "工作区").mkdir(exist_ok=True)
    (out / "文风").mkdir(exist_ok=True)
    (out / ".gitignore").write_text(".cache/\n工作区/\n", encoding="utf-8")
    _write_book_yaml(out, state)

    style = project_root / "设定集" / "风格契约.md"
    if style.exists():
        _copy(style, out / "文风" / "风格宪法.md")
    else:
        report.skipped.append("文风/风格宪法.md（v6 无 设定集/风格契约.md，留空由作者补写）")
    report.skipped.append("大纲/承诺/（需从总纲抽取承诺条目，属 S19 后置）")
    report.skipped.append("审查报告/（v6 产物，保留在源项目，不迁移）")
    report.skipped.append("设定集/增强设定/（v6 侧卡片契约，v7 由角色卡/世界观承接）")

    _migrate_chapters(project_root, out, vols, report)
    _migrate_settings(project_root, out, state, report)
    _migrate_summaries(project_root, out, report)
    _migrate_outlines(project_root, out, report)

    if use_git:
        _git_init(out, report.chapters)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="v6 书项目 → v7 story-repo 只读迁移（S16/E1）")
    parser.add_argument("--project-root", required=True, help="v6 书项目根目录")
    parser.add_argument("--output", required=True, help="输出的 v7 story-repo 目录（必须不存在）")
    parser.add_argument("--no-git", action="store_true", help="跳过 git init 与初始提交")
    args = parser.parse_args()

    report = migrate_project(args.project_root, args.output, use_git=not args.no_git)
    for line in report.as_lines():
        print(line)


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    main()
