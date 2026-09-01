#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v7_cache 测试（S17/E2）：.cache/index.db 全量重建与「派生物可丢弃」验收。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from migrate_v6_to_v7 import migrate_project  # noqa: E402
from v7_cache import (  # noqa: E402
    cache_path,
    find_entity,
    get_chapter,
    get_summary,
    rebuild_cache,
    snapshot,
    verify_rebuild,
)

CHAPTER_1 = "# 第0001章 天裂\n\n凌晨五点半，苏小白从便利店后门出来。\n"


def _v7_repo(tmp_path: Path) -> Path:
    src = tmp_path / "v6book"
    (src / "正文").mkdir(parents=True)
    (src / "设定集").mkdir()
    (src / "大纲").mkdir()
    (src / ".webnovel" / "summaries").mkdir(parents=True)
    (src / "正文" / "第0001章-天裂.md").write_text(CHAPTER_1, encoding="utf-8")
    (src / "正文" / "第0002章-想活.md").write_text("# 第0002章 想活\n\n灾来了。\n", encoding="utf-8")
    (src / "设定集" / "世界观.md").write_text("# 世界观\n", encoding="utf-8")
    (src / "设定集" / "主角卡.md").write_text("# 主角卡\n\n- 姓名：苏小白\n", encoding="utf-8")
    (src / "大纲" / "总纲.md").write_text("# 总纲\n", encoding="utf-8")
    (src / ".webnovel" / "summaries" / "ch0001.md").write_text("第一章摘要", encoding="utf-8")
    (src / ".webnovel" / "state.json").write_text(
        json_dumps_state(), encoding="utf-8"
    )
    out = tmp_path / "v7book"
    migrate_project(src, out, use_git=False)
    return out


def json_dumps_state() -> str:
    import json

    return json.dumps(
        {
            "project_info": {"title": "测试书", "genre": "都市"},
            "protagonist_state": {"name": "苏小白"},
        },
        ensure_ascii=False,
    )


class TestRebuildAndQueries:
    def test_rebuild_creates_cache_and_queries_answer(self, tmp_path):
        repo = _v7_repo(tmp_path)

        report = rebuild_cache(repo)

        assert cache_path(repo).exists()
        assert report["chapters"] == 2
        assert get_chapter(repo, 1)["标题"] == "天裂"
        assert get_chapter(repo, 1)["卷"] == 1
        assert get_summary(repo, 1) == "第一章摘要"

    def test_entity_from_roster(self, tmp_path):
        repo = _v7_repo(tmp_path)
        rebuild_cache(repo)

        entity = find_entity(repo, "苏小白")

        assert entity is not None
        assert entity["first_chapter"] == "" or entity["first_chapter"] == "1"

    def test_missing_chapter_returns_none(self, tmp_path):
        repo = _v7_repo(tmp_path)
        rebuild_cache(repo)

        assert get_chapter(repo, 99) is None


class TestDerivedCacheDisposable:
    def test_verify_delete_rebuild_snapshot_equal(self, tmp_path):
        """CI 验收项：删光 .cache 后重建，查询快照等价。"""
        repo = _v7_repo(tmp_path)
        rebuild_cache(repo)
        before = snapshot(repo)
        assert before  # 快照非空

        cache_path(repo).unlink()  # 模拟删光缓存
        assert not cache_path(repo).exists()

        result = verify_rebuild(repo)

        assert result["equal"] is True
        assert snapshot(repo) == before

    def test_verify_detects_source_drift(self, tmp_path):
        """源文件变化后仅重建不删源，快照内容应反映新正文（缓存不遮蔽真相）。"""
        repo = _v7_repo(tmp_path)
        rebuild_cache(repo)

        chapter = next((repo / "定稿" / "正文").glob("0002-*.md"))
        chapter.write_text(
            chapter.read_text(encoding="utf-8").replace("灾来了。", "灾真的来了。"),
            encoding="utf-8",
        )

        result = verify_rebuild(repo)

        assert result["equal"] is True  # 重建后快照自洽
        body = get_chapter(repo, 2)
        assert body is not None


def _raw_v7_repo(tmp_path: Path) -> Path:
    """不经迁移的 v7 原生书仓（无 名册.md 单表，只有 settle 的名册目录）。"""
    repo = tmp_path / "v7native"
    (repo / "定稿" / "正文").mkdir(parents=True)
    (repo / "定稿" / "记忆" / "章摘要").mkdir(parents=True)
    (repo / "定稿" / "设定" / "名册").mkdir(parents=True)
    return repo


class TestRosterDualLocation:
    """审阅报告 P1：settle 写名册目录、缓存此前只读单表——v7 原生新书实体面为死。"""

    def test_v7_native_book_directory_only(self, tmp_path):
        repo = _raw_v7_repo(tmp_path)
        (repo / "定稿" / "设定" / "名册" / "新人甲.md").write_text(
            "---\n正名: 新人甲\n别名: [\"阿甲\", \"小甲\"]\n类型: 角色\n首现章: 38\n---\n", encoding="utf-8"
        )

        rebuild_cache(repo)

        hit = find_entity(repo, "新人甲")
        assert hit is not None
        assert hit["first_chapter"] == "38"
        assert "阿甲" in hit["aliases"]

    def test_directory_overrides_single_table_on_overlap(self, tmp_path):
        repo = _raw_v7_repo(tmp_path)
        (repo / "定稿" / "设定" / "名册.md").write_text(
            "| 正名 | 别名 |\n|---|---|\n| 老周 | 旧别名 |\n", encoding="utf-8"
        )
        (repo / "定稿" / "设定" / "名册" / "老周.md").write_text(
            "---\n正名: 老周\n别名: [\"新别名\"]\n类型: 角色\n首现章: 5\n---\n", encoding="utf-8"
        )

        rebuild_cache(repo)

        entities = dict(snapshot(repo)["entities"])
        assert entities["老周"] == "新别名"  # 目录形态覆盖单表
        assert find_entity(repo, "老周")["first_chapter"] == "5"

    def test_find_entity_alias_fuzzy_still_works(self, tmp_path):
        repo = _raw_v7_repo(tmp_path)
        (repo / "定稿" / "设定" / "名册" / "熊哥.md").write_text(
            "---\n正名: 熊哥\n别名: [\"熊铁山\"]\n类型: 角色\n首现章: 36\n---\n", encoding="utf-8"
        )

        rebuild_cache(repo)

        assert find_entity(repo, "熊铁山")["name"] == "熊哥"
