#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T22（M5）上下文连续性包测试。

对应方案：03 R1/R10/R5（W1=F-01 上一章原文、F-11 截断方向、F-04 文风层保护）、
08 T22。
契约：load-context 含 prev_chapter_tail（v7/v6 双布局，front matter 剥离）与
stale_notes（作者已改未消费提醒）；recent_summaries 新章优先截断（ch-1 完整）；
饱和下三段（prev_chapter_tail/author_style_patterns/style_contract）保全。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def _write_v7_body(root: Path, chapter: int, body: str) -> None:
    body_dir = root / "定稿" / "正文"
    body_dir.mkdir(parents=True, exist_ok=True)
    (body_dir / f"{chapter:04d}-章{chapter}.md").write_text(
        f"---\n章号: {chapter}\n标题: 章{chapter}\n---\n# 第{chapter}章\n\n{body}\n",
        encoding="utf-8",
        newline="\n",
    )


@pytest.fixture()
def cfg(tmp_path: Path):
    from data_modules.config import DataModulesConfig

    config = DataModulesConfig.from_project_root(tmp_path)
    config.ensure_dirs()
    config.state_file.write_text("{}", encoding="utf-8")
    return config


class TestPrevChapterTail:
    def test_reads_v7_layout_tail_with_prefix(self, cfg, tmp_path: Path):
        from data_modules.memory_contract_adapter import read_prev_chapter_tail

        body = "第一段。" + "语气细节。" * 400 + "结尾钩子：门外有人叫他。"
        _write_v7_body(tmp_path, 36, body)

        tail = read_prev_chapter_tail(tmp_path, 37, 200)

        assert tail.startswith("……")
        assert len(tail) <= 202
        assert tail.endswith("门外有人叫他。"), "取尾段原文"

    def test_reads_v6_layout_fallback(self, cfg, tmp_path: Path):
        from data_modules.memory_contract_adapter import read_prev_chapter_tail

        body_dir = tmp_path / "正文"
        body_dir.mkdir(parents=True, exist_ok=True)
        (body_dir / "第0035章.md").write_text("正文" * 300 + "结尾。" , encoding="utf-8")

        tail = read_prev_chapter_tail(tmp_path, 36, 100)

        assert tail.startswith("……") and tail.endswith("结尾。")

    def test_missing_body_returns_empty(self, tmp_path: Path):
        from data_modules.memory_contract_adapter import read_prev_chapter_tail

        assert read_prev_chapter_tail(tmp_path, 5, 200) == ""


class TestLoadContextSections:
    def test_load_context_contains_tail_and_stale_notes(self, cfg, tmp_path: Path):
        from data_modules.author_journal import mark_stale
        from data_modules.memory_contract_adapter import MemoryContractAdapter

        _write_v7_body(tmp_path, 1, "上章正文。" + "细节。" * 300 + "结尾钩子。")
        mark_stale(tmp_path, target="chapter:0002", reason="章纲被作者修改")

        pack = MemoryContractAdapter(cfg).load_context(2)

        tail = pack.sections.get("prev_chapter_tail")
        assert tail and tail.startswith("……") and tail.endswith("结尾钩子。")
        stale = pack.sections.get("stale_notes")
        assert stale and stale[0]["target"] == "chapter:0002"
        assert "作者" in stale[0]["reason"]

    def test_recent_summaries_newest_first_truncation(self, cfg, tmp_path: Path, monkeypatch):
        """R10/F-11：配额不足时 ch-2 先被截、ch-1 完整。"""
        from data_modules import context_budget
        from data_modules.memory_contract_adapter import MemoryContractAdapter

        adapter = MemoryContractAdapter(cfg)
        for ch in (1, 2):
            summary_path = cfg.webnovel_dir / "summaries" / f"ch{ch:04d}.md"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(f"第{ch}章摘要" + "内" * 480, encoding="utf-8")
        monkeypatch.setitem(context_budget.SECTION_QUOTAS, "recent_summaries", 600)

        pack = adapter.load_context(3)
        # adapter 在 import 时绑定 enforce_budget（模块级导入），monkeypatch 配额即可生效
        summaries = pack.sections.get("recent_summaries") or {}

        assert summaries, "摘要在饱和下仍保留"
        ch1 = summaries.get("ch0002", "")  # ch-1 = 第 2 章（目标章 3 的上一章）
        assert ch1.startswith("第2章摘要") and "预算截断" not in ch1, "紧邻上一章摘要完整"
