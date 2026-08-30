#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""migrate_v6_to_v7 测试（S16/E1）：v6 → v7 story-repo 只读迁移。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from migrate_v6_to_v7 import migrate_project  # noqa: E402

CHAPTER_1 = "# 第0001章 天裂\n\n凌晨五点半，苏小白从便利店后门出来。\n"
CHAPTER_2 = "# 第0002章 想活\n\n「想活？先吃下这场灾。」\n"
WORLD = "# 世界观\n\n天裂横在头顶，一天宽一线。\n"


def _v6_project(tmp_path: Path) -> Path:
    src = tmp_path / "v6book"
    (src / "正文").mkdir(parents=True)
    (src / "设定集").mkdir()
    (src / "大纲").mkdir()
    (src / ".webnovel" / "summaries").mkdir(parents=True)
    (src / "正文" / "第0001章-天裂.md").write_text(CHAPTER_1, encoding="utf-8")
    (src / "正文" / "第0002章-想活.md").write_text(CHAPTER_2, encoding="utf-8")
    (src / "设定集" / "世界观.md").write_text(WORLD, encoding="utf-8")
    (src / "设定集" / "主角卡.md").write_text("# 主角卡\n\n- 姓名：苏小白\n", encoding="utf-8")
    (src / "大纲" / "总纲.md").write_text("# 总纲\n\n吃灾修行。\n", encoding="utf-8")
    (src / "大纲" / "第1卷-详细大纲.md").write_text("### 第1章：天裂\n", encoding="utf-8")
    (src / "大纲" / "第1卷-时间线.md").write_text(
        "| 章 | 时间 |\n|---|---|\n| 第1章 | 末世第1天 |\n| 第2章 | 末世第1天 |\n",
        encoding="utf-8",
    )
    (src / ".webnovel" / "summaries" / "ch0001.md").write_text("第一章摘要", encoding="utf-8")
    (src / ".webnovel" / "state.json").write_text(
        json.dumps(
            {
                "project_info": {"title": "测试书", "genre": "都市", "target_words": 100000, "target_chapters": 50},
                "protagonist_state": {"name": "苏小白"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return src


class TestMigrateProject:
    def test_migrates_expected_structure(self, tmp_path):
        src = _v6_project(tmp_path)
        out = tmp_path / "v7book"

        report = migrate_project(src, out, use_git=False)

        assert (out / "book.yaml").exists()
        book = (out / "book.yaml").read_text(encoding="utf-8")
        assert "spec_version: \"7.0\"" in book
        assert "书名: 测试书" in book
        assert "类型: 都市" in book

        body1 = out / "定稿" / "正文" / "0001-天裂.md"
        assert body1.exists()
        text = body1.read_text(encoding="utf-8")
        assert text.startswith("---\n章号: 1")
        assert "标题: 天裂" in text
        assert "字数:" in text
        assert "苏小白从便利店后门出来" in text  # 正文无损

        assert (out / "定稿" / "设定" / "世界观.md").exists()
        assert (out / "定稿" / "设定" / "角色" / "苏小白.md").exists()
        assert (out / "定稿" / "记忆" / "章摘要" / "0001.md").read_text(encoding="utf-8") == "第一章摘要"
        assert (out / "大纲" / "总纲.md").exists()
        assert (out / "大纲" / "卷纲" / "第01卷.md").exists()  # spec §2.1 零填充
        assert (out / "定稿" / "设定" / "时间线.md").exists()
        assert (out / ".gitignore").exists()

        assert report.chapters == 2
        assert report.skipped  # 范围外清单（承诺/审查报告/增强设定）显式透出

    def test_source_stays_read_only(self, tmp_path):
        src = _v6_project(tmp_path)
        before = {p: (p.stat().st_mtime, p.read_text(encoding="utf-8")) for p in src.rglob("*") if p.is_file()}

        migrate_project(src, tmp_path / "v7book", use_git=False)

        for p, (mtime, content) in before.items():
            assert p.exists(), f"源文件被删: {p}"
            assert p.read_text(encoding="utf-8") == content
            assert p.stat().st_mtime == mtime

    def test_rejects_existing_output(self, tmp_path):
        src = _v6_project(tmp_path)
        out = tmp_path / "v7book"
        out.mkdir()

        with pytest.raises(FileExistsError):
            migrate_project(src, out, use_git=False)

    def test_missing_chapter_body_dir_reports_zero(self, tmp_path):
        src = tmp_path / "empty"
        src.mkdir()
        (src / ".webnovel").mkdir(parents=True)
        (src / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")

        report = migrate_project(src, tmp_path / "out", use_git=False)

        assert report.chapters == 0
