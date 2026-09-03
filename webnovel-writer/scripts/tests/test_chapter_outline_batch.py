#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T8（M1）章纲批量生成测试。

对应方案：06 §2（章纲卡 front matter）、07 F-04、08 T8、02 P7（一次确认一批）。
契约：一批 ≤8 张；必填字段校验；批内自检（节点非空/字数范围/承诺格式）；
写入 状态: draft；confirm 翻转为 confirmed 并留 journal。
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.domain_contract import init_domain_skeleton

    init_domain_skeleton(tmp_path)
    return tmp_path


def _card(chapter: int, **over) -> dict:
    base = {
        "章节号": chapter,
        "标题": f"第{chapter}章标题",
        "卷": 2,
        "时间锚": f"第{chapter}日·夜",
        "节点": [f"CBN: 推进{chapter}", f"CEN: 钩子{chapter}"],
        "禁区": ["主角不得暴露金手指"],
        "承诺推进": [f"F-{chapter:03d}: 揭示部分真相"],
        "战力事件": [],
        "素材引用": ["桥段:TR-012"],
        "字数目标": 2400,
        "正文": f"# 第 {chapter} 章 章纲正文",
    }
    base.update(over)
    return base


class TestCreateBatch:
    def test_creates_draft_cards_with_front_matter(self, book: Path):
        from data_modules.chapter_outline_batch import create_chapter_batch, parse_chapter_card

        report = create_chapter_batch(book, [_card(39), _card(40), _card(41)])

        assert report["ok"] is True
        assert report["written"] == [39, 40, 41]
        fields, body = parse_chapter_card((book / "大纲" / "章纲" / "0039.md").read_text(encoding="utf-8"))
        assert fields["章节号"] == "39"
        assert fields["状态"] == "draft"
        assert fields["字数目标"] == "2400"
        assert "章纲正文" in body

    def test_batch_over_eight_rejected(self, book: Path):
        from data_modules.chapter_outline_batch import create_chapter_batch

        report = create_chapter_batch(book, [_card(100 + i) for i in range(9)])

        assert report["ok"] is False
        assert report["error"] == "batch_too_large"

    def test_duplicate_chapter_rejected(self, book: Path):
        from data_modules.chapter_outline_batch import create_chapter_batch

        report = create_chapter_batch(book, [_card(39), _card(39, 标题="另一标题")])

        assert report["ok"] is False
        assert report["error"] == "duplicate_chapter"

    def test_missing_required_field_rejected(self, book: Path):
        from data_modules.chapter_outline_batch import create_chapter_batch

        bad = _card(39)
        del bad["标题"]
        report = create_chapter_batch(book, [bad])

        assert report["ok"] is False
        assert report["error"] == "missing_field"

    def test_list_fields_round_trip(self, book: Path):
        from data_modules.chapter_outline_batch import create_chapter_batch, parse_chapter_card

        create_chapter_batch(book, [_card(39)])
        fields, _ = parse_chapter_card((book / "大纲" / "章纲" / "0039.md").read_text(encoding="utf-8"))

        assert fields["节点"] == ["CBN: 推进39", "CEN: 钩子39"]
        assert fields["承诺推进"] == ["F-039: 揭示部分真相"]


class TestSelfCheck:
    def test_empty_nodes_flagged(self, book: Path):
        from data_modules.chapter_outline_batch import self_check_batch

        problems = self_check_batch([_card(39, 节点=[])])

        assert any("节点" in p for p in problems)

    def test_word_target_out_of_range_flagged(self, book: Path):
        from data_modules.chapter_outline_batch import self_check_batch

        problems = self_check_batch([_card(39, 字数目标=50)])

        assert any("字数" in p for p in problems)

    def test_promise_format_flagged(self, book: Path):
        from data_modules.chapter_outline_batch import self_check_batch

        problems = self_check_batch([_card(39, 承诺推进=["没有前缀的承诺"])])

        assert any("承诺" in p for p in problems)

    def test_clean_card_no_problems(self, book: Path):
        from data_modules.chapter_outline_batch import self_check_batch

        assert self_check_batch([_card(39)]) == []

    def test_create_reports_self_check(self, book: Path):
        from data_modules.chapter_outline_batch import create_chapter_batch

        report = create_chapter_batch(book, [_card(39, 字数目标=50)])

        assert report["ok"] is True, "自检问题为 warning，不阻断创建"
        assert report["checks"], "自检问题应在报告中透出"


class TestConfirm:
    def test_confirm_flips_status_and_leaves_trail(self, book: Path):
        from data_modules.author_journal import read_journal
        from data_modules.chapter_outline_batch import confirm_chapter_batch, create_chapter_batch, parse_chapter_card

        create_chapter_batch(book, [_card(39), _card(40)])
        report = confirm_chapter_batch(book, [39, 40])

        assert report["ok"] is True
        for chapter in (39, 40):
            fields, _ = parse_chapter_card((book / "大纲" / "章纲" / f"{chapter:04d}.md").read_text(encoding="utf-8"))
            assert fields["状态"] == "confirmed"
        assert "adopt" in [e["action"] for e in read_journal(book)]

    def test_confirm_missing_chapter_fails(self, book: Path):
        from data_modules.chapter_outline_batch import confirm_chapter_batch

        report = confirm_chapter_batch(book, [99])
        assert report["ok"] is False
