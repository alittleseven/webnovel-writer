#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T21（M4）信息差与知识边界测试。

对应方案：06 §9（信息差条目表）、02 功能映射 A1（knowledge 合并知识边界输出）、
08 T21。
契约：解析 设定/信息差.md 表（信息点/知晓者/知晓章/泄露禁忌）；boundary 按章输出
每个信息点的知晓状态与未知清单（reviewer 知识边界维证据源）；实体过滤按 A1 口径
（该实体相关的每个信息点：谁知道、从哪章知道）；文件缺失优雅降级。
"""

from __future__ import annotations

from pathlib import Path

import pytest


INFO_GAP_MD = """# 信息差（谁知道什么）

| 信息点 | 知晓者 | 知晓章 | 泄露禁忌 |
|--------|--------|-------|----------|
| 主角能吃灾 | 苏小白 | 1 | 不得在第3卷前让名册角色知晓 |
| 账本真相 | 熊铁山 | 41 | 对主角隐瞒至卷三 |
| 灾雾源位置 | 苏小白、老周 | 99 | 卷四前不得公开 |
"""


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.domain_contract import init_domain_skeleton

    init_domain_skeleton(tmp_path)
    settings = tmp_path / "定稿" / "设定"
    settings.mkdir(parents=True, exist_ok=True)
    (settings / "信息差.md").write_text(INFO_GAP_MD, encoding="utf-8")
    return tmp_path


class TestParse:
    def test_parse_table_rows(self, book: Path):
        from data_modules.info_gap import parse_info_gap

        facts = parse_info_gap(book)

        assert len(facts) == 3
        assert facts[0] == {
            "信息点": "主角能吃灾",
            "知晓者": ["苏小白"],
            "知晓章": 1,
            "泄露禁忌": "不得在第3卷前让名册角色知晓",
        }
        assert facts[2]["知晓者"] == ["苏小白", "老周"], "知晓者顿号分隔还原列表"

    def test_parse_missing_file_returns_empty(self, tmp_path: Path):
        from data_modules.domain_contract import init_domain_skeleton
        from data_modules.info_gap import parse_info_gap

        init_domain_skeleton(tmp_path)
        assert parse_info_gap(tmp_path) == []


class TestBoundary:
    def test_boundary_marks_known_and_unknown(self, book: Path):
        from data_modules.info_gap import boundary

        report = boundary(book, chapter=41)

        assert report["ok"] is True
        assert report["chapter"] == 41
        by_fact = {f["信息点"]: f for f in report["facts"]}
        assert by_fact["主角能吃灾"]["该章已知"] is True
        assert by_fact["账本真相"]["该章已知"] is True, "知晓章 41 = 第 41 章已知晓"
        assert by_fact["灾雾源位置"]["该章已知"] is False
        assert report["unknown_at_chapter"] == ["灾雾源位置"], "reviewer 证据：本章不得被使用的未知信息"

    def test_boundary_entity_filter(self, book: Path):
        from data_modules.info_gap import boundary

        report = boundary(book, chapter=10, entity="苏小白")

        assert [f["信息点"] for f in report["facts"]] == ["主角能吃灾", "灾雾源位置"], "A1：该实体相关的信息点"
        xiong = boundary(book, chapter=10, entity="熊铁山")
        assert [f["信息点"] for f in xiong["facts"]] == ["账本真相"]
        assert xiong["facts"][0]["该章已知"] is False, "第 10 章：知晓章 41 尚未揭晓"

    def test_boundary_without_file_degrades(self, tmp_path: Path):
        from data_modules.domain_contract import init_domain_skeleton
        from data_modules.info_gap import boundary

        init_domain_skeleton(tmp_path)
        report = boundary(tmp_path, chapter=1)

        assert report["ok"] is True
        assert report["facts"] == []
        assert report["note"]
