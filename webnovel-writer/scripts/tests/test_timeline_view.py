#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T9（M1）卷纲时间线视图测试。

对应方案：07 F-03、08 T9。
契约：时间线视图 = 章纲卡（时间锚/节点/承诺/战力事件）按章排序导出为可解析表格；
作者改视图 → sync_view_to_cards 列 diff（dry-run），--apply 才回写章纲卡。
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.chapter_outline_batch import create_chapter_batch
    from data_modules.domain_contract import init_domain_skeleton

    init_domain_skeleton(tmp_path)
    (tmp_path / "大纲" / "卷纲").mkdir(parents=True, exist_ok=True)
    create_chapter_batch(
        tmp_path,
        [
            {
                "章节号": 39,
                "标题": "纸债",
                "卷": 2,
                "时间锚": "第41日·夜",
                "节点": ["CBN: 发现账本异常", "CEN: 熊铁山出手"],
                "禁区": [],
                "承诺推进": ["F-003: 揭示部分真相"],
                "战力事件": ["凝罡突破"],
                "素材引用": [],
                "字数目标": 2400,
                "正文": "# 39",
            },
            {
                "章节号": 40,
                "标题": "码头",
                "卷": 2,
                "时间锚": "第42日·晨",
                "节点": ["CBN: 码头对峙"],
                "禁区": [],
                "承诺推进": [],
                "战力事件": [],
                "素材引用": [],
                "字数目标": 2300,
                "正文": "# 40",
            },
        ],
    )
    return tmp_path


class TestBuildView:
    def test_writes_view_file_sorted_by_chapter(self, book: Path):
        from data_modules.timeline_view import build_timeline_view

        report = build_timeline_view(book, volume=2)

        assert report["ok"] is True
        view = (book / "大纲" / "卷纲" / "第02卷-时间线.md").read_text(encoding="utf-8")
        assert "<!-- timeline-view" in view
        # 精确匹配表格行首：generated 时间戳可能含 "39"/"40" 数字，裸子串会撞车（时间敏感假失败）
        assert view.index("| 39 |") < view.index("| 40 |"), "按章排序"
        assert "发现账本异常" in view
        assert "F-003" in view
        assert "凝罡突破" in view

    def test_duplicate_anchor_flagged(self, book: Path):
        from data_modules.chapter_outline_batch import create_chapter_batch
        from data_modules.timeline_view import build_timeline_view

        create_chapter_batch(
            book,
            [{
                "章节号": 41,
                "标题": "x",
                "卷": 2,
                "时间锚": "第41日·夜",  # 与 39 重复
                "节点": ["CBN: a"],
                "禁区": [],
                "承诺推进": [],
                "战力事件": [],
                "素材引用": [],
                "字数目标": 2000,
                "正文": "# 41",
            }],
        )
        report = build_timeline_view(book, volume=2)

        assert any("重复" in w for w in report["warnings"])

    def test_no_cards_writes_note_only(self, book: Path):
        from data_modules.timeline_view import build_timeline_view

        report = build_timeline_view(book, volume=9)

        assert report["ok"] is True
        assert report["rows"] == 0
        view = (book / "大纲" / "卷纲" / "第09卷-时间线.md").read_text(encoding="utf-8")
        assert "暂无章纲卡" in view


class TestReverseSync:
    def test_author_view_edit_detected_dry_run(self, book: Path):
        from data_modules.timeline_view import build_timeline_view, sync_view_to_cards

        build_timeline_view(book, volume=2)
        view_path = book / "大纲" / "卷纲" / "第02卷-时间线.md"
        view_path.write_text(
            view_path.read_text(encoding="utf-8").replace("第41日·夜", "第40日·夜"), encoding="utf-8"
        )

        report = sync_view_to_cards(book, volume=2, dry_run=True)

        diffs = report["diffs"]
        assert any(d["chapter"] == 39 and d["new"] == "第40日·夜" for d in diffs), "作者改视图被识别"
        # dry-run 不回写章纲卡
        from data_modules.chapter_outline_batch import parse_chapter_card

        fields, _ = parse_chapter_card((book / "大纲" / "章纲" / "0039.md").read_text(encoding="utf-8"))
        assert fields["时间锚"] == "第41日·夜"

    def test_apply_writes_back_to_cards(self, book: Path):
        from data_modules.timeline_view import build_timeline_view, sync_view_to_cards

        build_timeline_view(book, volume=2)
        view_path = book / "大纲" / "卷纲" / "第02卷-时间线.md"
        view_path.write_text(
            view_path.read_text(encoding="utf-8").replace("第41日·夜", "第40日·夜"), encoding="utf-8"
        )

        report = sync_view_to_cards(book, volume=2, dry_run=False)

        assert report["applied"] >= 1
        from data_modules.chapter_outline_batch import parse_chapter_card

        fields, _ = parse_chapter_card((book / "大纲" / "章纲" / "0039.md").read_text(encoding="utf-8"))
        assert fields["时间锚"] == "第40日·夜"

    def test_missing_view_returns_empty_diffs(self, book: Path):
        from data_modules.timeline_view import sync_view_to_cards

        report = sync_view_to_cards(book, volume=2, dry_run=True)
        assert report["diffs"] == []
