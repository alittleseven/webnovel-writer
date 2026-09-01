#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v7_write 测试：垂直切片写路径（S19/E3）。

夹具 = 最小 v7 story-repo（迁移器实际产物约定：chNNNN.md + 记忆/章摘要/NNNN.md +
设定/名册/<正名>.md）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from v7_write import (  # noqa: E402
    TOTAL_BUDGET_DEFAULT,
    V7_SECTION_QUOTAS,
    build_context_pack,
    run_checks,
    settle,
    write_decision_card,
)

SUMMARY_0034 = "苏小白当众立规矩稳人心，赵姓汉子拆开包袱留下；暗处有人把仓库布防写给熊铁山。"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _v7_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "定稿" / "正文").mkdir(parents=True)
    (repo / "定稿" / "记忆" / "章摘要").mkdir(parents=True)
    (repo / "定稿" / "设定" / "名册").mkdir(parents=True)
    (repo / "定稿" / "设定" / "时间线").mkdir(parents=True)
    (repo / "工作区").mkdir()
    (repo / "book.yaml").write_text("书名: 测试书\n作者: 测试\n", encoding="utf-8")
    (repo / ".gitignore").write_text(".cache/\n工作区/\n", encoding="utf-8")
    body = "正文" + "内" * 2800
    (repo / "定稿" / "正文" / "ch0034.md").write_text(
        "---\nspec_stage: manuscript\nchapter: 34\ntitle: 试炼\nword_count: 2800\n---\n" + body,
        encoding="utf-8",
    )
    (repo / "定稿" / "记忆" / "章摘要" / "0034.md").write_text(SUMMARY_0034, encoding="utf-8")
    (repo / "定稿" / "设定" / "名册" / "苏小白.md").write_text(
        "---\n正名: 苏小白\n别名: [苏哥]\n类型: 角色\n首现章: 1\n---\n", encoding="utf-8"
    )
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@local")
    _git(repo, "config", "user.name", "test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo


def _decision(chapter: int = 37) -> dict:
    return {
        "chapter": chapter,
        "title": "不眠夜",
        "pov": "苏小白",
        "time_anchor": "末世第18天 白天",
        "goal": "消化熊铁山的放话，收拢内患，着手备战",
        "nodes": ["内患收拢", "备战布置", "暗哨疑云"],
        "forbidden": ["不写城北决战", "风暴不来"],
        "promises": [],
        "waiver": "迁移仓无承诺档案，切片章豁免承诺结转",
        "contract": ["内患收拢：赵姓汉子留下并领了备战差事", "暗哨情报线开启"],
        "entities": ["苏小白", "林知夏", "老周", "老六", "赵姓汉子"],
        "new_entities": [
            {"name": "赵姓汉子", "type": "角色", "aliases": ["赵汉子"]},
            {"name": "熊铁山", "type": "角色", "aliases": ["熊哥"]},
        ],
    }


class TestDecisionCard:
    def test_writes_markdown_with_fields(self, tmp_path):
        repo = _v7_repo(tmp_path)
        d = _decision()

        path = write_decision_card(repo, d)

        assert Path(path).exists()
        text = Path(path).read_text(encoding="utf-8")
        assert "决策卡" in text and "0037" in text
        assert "不眠夜" in text and "内患收拢" in text
        assert "豁免" in text


class TestContextPack:
    def test_pack_within_budget_and_has_sections(self, tmp_path):
        repo = _v7_repo(tmp_path)
        d = _decision()

        md, stats = build_context_pack(repo, d)

        assert "决策卡" in md and "前情摘要" in md and "名册" in md
        assert stats["used"] <= stats["total_budget"]
        assert "苏小白当众立规矩" in md  # v7_cache.get_summary 命中上章摘要

    def test_pack_entities_resolved_from_cache(self, tmp_path):
        repo = _v7_repo(tmp_path)
        d = _decision()

        md, _ = build_context_pack(repo, d)

        assert "苏小白" in md  # find_entity 命中名册


class TestChecks:
    def test_clean_draft_passes(self, tmp_path):
        repo = _v7_repo(tmp_path)
        d = _decision()
        draft = "# 不眠夜\n\n" + "苏小白看着围墙外的风暴云。" * 120

        report = run_checks(repo, d, draft)

        assert report["word_count"] > 800
        assert report["placeholders"] == []
        assert report["title_ok"] is True
        assert report["promise_ok"] is True
        assert report["ok"] is True

    def test_placeholder_and_title_mismatch_fail(self, tmp_path):
        repo = _v7_repo(tmp_path)
        d = _decision()
        draft = "# 错标题\n\n" + "正文[待补充]占位。" * 100

        report = run_checks(repo, d, draft)

        assert report["placeholders"]
        assert report["title_ok"] is False
        assert report["ok"] is False

    def test_new_name_advisory(self, tmp_path):
        repo = _v7_repo(tmp_path)
        d = _decision()
        draft = "# 不眠夜\n\n" + "「张三丰」从门外走进来。" * 120

        report = run_checks(repo, d, draft)

        assert "张三丰" in report["new_name_candidates"]


class TestSettle:
    def test_settle_writes_files_and_commits(self, tmp_path):
        repo = _v7_repo(tmp_path)
        d = _decision()
        body = "# 不眠夜\n\n" + "苏小白看着围墙外的风暴云。" * 120
        (repo / "工作区" / "草稿-0037.md").write_text(body, encoding="utf-8")

        result = settle(repo, d, draft_path=repo / "工作区" / "草稿-0037.md", summary="内患收拢，备战开始。", commit=True)

        chapter_file = repo / "定稿" / "正文" / "0037-不眠夜.md"
        assert chapter_file.exists()
        text = chapter_file.read_text(encoding="utf-8")
        assert "章号: 37" in text and "标题: 不眠夜" in text and "字数:" in text
        assert (repo / "定稿" / "记忆" / "章摘要" / "0037.md").exists()
        assert result["committed"] is True
        log = subprocess.run(["git", "-C", str(repo), "log", "--oneline", "-1"], capture_output=True, text=True).stdout
        assert "0037" in log

    def test_settle_refuses_when_already_settled(self, tmp_path):
        repo = _v7_repo(tmp_path)
        d = _decision()
        body = "# 不眠夜\n\n" + "苏小白看着围墙外的风暴云。" * 120
        (repo / "工作区" / "草稿-0037.md").write_text(body, encoding="utf-8")
        (repo / "定稿" / "正文" / "0037-不眠夜.md").write_text(body, encoding="utf-8")

        with pytest.raises(RuntimeError, match="唯一写入路径"):
            settle(repo, d, draft_path=repo / "工作区" / "草稿-0037.md", summary="s", commit=False)

    def test_settle_refuses_failing_checks_without_side_effects(self, tmp_path):
        repo = _v7_repo(tmp_path)
        d = _decision()
        draft = repo / "工作区" / "草稿-0037.md"
        draft.write_text("# 错标题\n\n" + "占位[待补充]。" * 50, encoding="utf-8")

        with pytest.raises(RuntimeError, match="机检"):
            settle(repo, d, draft_path=draft, summary="s", commit=False)

        assert not (repo / "定稿" / "正文" / "0037-不眠夜.md").exists()
        assert not (repo / "定稿" / "记忆" / "章摘要" / "0037.md").exists()

    def test_settle_rolls_back_on_midway_failure(self, tmp_path):
        """spec 不变量：settle 要么完成 commit，要么不落任何定稿文件。"""
        repo = _v7_repo(tmp_path)
        d = _decision()
        body = "# 不眠夜\n\n" + "苏小白看着围墙外的风暴云。" * 120
        draft = repo / "工作区" / "草稿-0037.md"
        draft.write_text(body, encoding="utf-8")
        # 第二个新实体的落点被目录占位 → 写入中途失败，模拟崩溃
        (repo / "定稿" / "设定" / "名册" / "熊铁山.md").mkdir(parents=True)

        with pytest.raises(RuntimeError, match="回滚|roll back"):
            settle(repo, d, draft_path=draft, summary="s", commit=False)

        assert not (repo / "定稿" / "正文" / "0037-不眠夜.md").exists()
        assert not (repo / "定稿" / "记忆" / "章摘要" / "0037.md").exists()
        assert not (repo / "定稿" / "设定" / "名册" / "赵姓汉子.md").exists()  # 已写的也回滚


    def test_settle_refreshes_cache_for_next_chapter(self, tmp_path):
        """增量审阅 P1-2：settle 后不手动 rebuild，下一章查询面即含新摘要/新实体。"""
        from v7_cache import find_entity, get_summary, rebuild_cache

        repo = _v7_repo(tmp_path)
        rebuild_cache(repo)  # settle 前的缓存：不含第 37 章
        d = _decision()
        body = "# 不眠夜\n\n" + "苏小白看着围墙外的风暴云。" * 120
        (repo / "工作区" / "草稿-0037.md").write_text(body, encoding="utf-8")

        result = settle(
            repo, d, draft_path=repo / "工作区" / "草稿-0037.md", summary="内患收拢，备战开始。", commit=False
        )

        assert result["cache_rebuilt"] is True
        assert get_summary(repo, 37) == "内患收拢，备战开始。"
        assert find_entity(repo, "赵姓汉子")["name"] == "赵姓汉子"


class TestContextPackBookBudget:
    """S23：book.yaml context_budget 覆盖（显式参数 > book.yaml > 常量）+ 截断汇总信号。"""

    @staticmethod
    def _write_prev_chapter(repo: Path, chars: int = 3000) -> None:
        body = "夜" * chars
        (repo / "定稿" / "正文" / "0036-放话.md").write_text(
            "---\n章号: 36\n标题: 放话\n字数: 3000\n---\n" + body, encoding="utf-8"
        )

    def test_book_yaml_section_override_extends_tail(self, tmp_path):
        repo = _v7_repo(tmp_path)
        self._write_prev_chapter(repo)
        (repo / "book.yaml").write_text(
            "书名: 测试书\ncontext_budget:\n  sections:\n    prev_chapter_tail: 1600\n",
            encoding="utf-8",
        )

        md, stats = build_context_pack(repo, _decision())

        assert stats["sections"]["prev_chapter_tail"] == 1600
        tail = md.split("上一章结尾", 1)[1]
        assert tail.count("夜") > 1200  # 默认 1200 会截断，book.yaml 覆盖生效

    def test_book_yaml_total_override_and_explicit_arg_wins(self, tmp_path):
        repo = _v7_repo(tmp_path)
        (repo / "book.yaml").write_text("书名: 测试书\ncontext_budget:\n  total: 3000\n", encoding="utf-8")

        _, stats = build_context_pack(repo, _decision())
        assert stats["total_budget"] == 3000

        _, stats2 = build_context_pack(repo, _decision(), total_budget=20000)
        assert stats2["total_budget"] == 20000  # 显式参数 > book.yaml

    def test_no_override_zero_change(self, tmp_path):
        repo = _v7_repo(tmp_path)

        _, stats = build_context_pack(repo, _decision())

        assert stats["sections"] == V7_SECTION_QUOTAS
        assert stats["total_budget"] == TOTAL_BUDGET_DEFAULT
        assert stats["truncated_sections"] == []

    def test_truncated_sections_reported(self, tmp_path):
        repo = _v7_repo(tmp_path)
        self._write_prev_chapter(repo)
        (repo / "book.yaml").write_text(
            "书名: 测试书\ncontext_budget:\n  sections:\n    prev_chapter_tail: 100\n",
            encoding="utf-8",
        )

        _, stats = build_context_pack(repo, _decision())

        assert "prev_chapter_tail" in stats["truncated_sections"]
        assert 0 < stats["budget_used_ratio"] <= 1.0
