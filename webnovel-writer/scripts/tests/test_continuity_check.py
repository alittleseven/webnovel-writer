#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T29（M6）时间线年龄推演与命名冲突检查测试。

对应方案：02 A4（timeline-check 升级：年龄/修龄推演列）、A5（名册新增与既有实体
相似度检查，编辑距离）、08 T29。
契约：时间锚「第N天」可解析时时间线视图追加主角年龄/修龄列（book.yaml 主角年龄为
基准；无基准则不加列）；name-check 对名册正名/别名做编辑距离+包含+相似度检查，
撞名被报出。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def _make_card(root: Path, chapter: int, anchor: str) -> None:
    from data_modules.chapter_outline_batch import create_chapter_batch

    create_chapter_batch(
        root,
        [{
            "章节号": chapter, "标题": f"章{chapter}", "卷": 1, "时间锚": anchor,
            "节点": [f"CBN: 事件{chapter}"], "字数目标": 2000,
        }],
    )


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.domain_contract import init_domain_skeleton

    init_domain_skeleton(tmp_path)
    roster = tmp_path / "定稿" / "设定" / "名册"
    roster.mkdir(parents=True, exist_ok=True)
    (roster / "苏小白.md").write_text(
        '---\n正名: 苏小白\n别名: ["苏哥", "小白"]\n类型: 角色\n首现章: 1\n---\n', encoding="utf-8"
    )
    (roster / "林知夏.md").write_text(
        "---\n正名: 林知夏\n别名: []\n类型: 角色\n首现章: 2\n---\n", encoding="utf-8"
    )
    return tmp_path


class TestAgeDerivation:
    def test_age_columns_appended_when_base_configured(self, book: Path):
        from data_modules.continuity_check import derive_age_columns
        from data_modules.timeline_view import build_timeline_view

        (book / "book.yaml").write_text(
            'spec_version: "7.0"\n书名: 测试\n主角年龄: 24\n觉醒日: 1\n', encoding="utf-8"
        )
        _make_card(book, 1, "末世第1天")
        _make_card(book, 2, "末世第370天")
        build_timeline_view(book, volume=1)

        columns = derive_age_columns(book, volume=1)
        by_chapter = {c["章"]: c for c in columns}

        assert by_chapter[1]["年龄"] == 24 and by_chapter[1]["修龄"] == 0
        assert by_chapter[2]["年龄"] == 25, "370 天跨年：24+1"
        assert by_chapter[2]["修龄"] == 369

    def test_view_contains_age_column(self, book: Path):
        from data_modules.timeline_view import build_timeline_view

        (book / "book.yaml").write_text('书名: 测试\n主角年龄: 24\n觉醒日: 1\n', encoding="utf-8")
        _make_card(book, 1, "末世第100天")
        report = build_timeline_view(book, volume=1)

        view = Path(report["view_path"]).read_text(encoding="utf-8")
        assert "主角年龄" in view and "修龄" in view

    def test_no_base_age_no_column(self, book: Path):
        from data_modules.continuity_check import derive_age_columns
        from data_modules.timeline_view import build_timeline_view

        _make_card(book, 1, "末世第5天")
        build_timeline_view(book, volume=1)

        assert derive_age_columns(book, volume=1) == []
        view_path = book / "大纲" / "卷纲" / "第01卷-时间线.md"
        assert "主角年龄" not in view_path.read_text(encoding="utf-8")

    def test_unparsable_anchor_shows_dash(self, book: Path):
        from data_modules.continuity_check import derive_age_columns, parse_anchor_day
        from data_modules.timeline_view import build_timeline_view

        (book / "book.yaml").write_text('书名: 测试\n主角年龄: 24\n觉醒日: 1\n', encoding="utf-8")
        _make_card(book, 1, "某个雨夜")
        build_timeline_view(book, volume=1)

        assert parse_anchor_day("某个雨夜") is None
        columns = derive_age_columns(book, volume=1)
        assert columns and columns[0]["年龄"] == "—"


class TestNameConflict:
    def test_similar_name_flagged_by_distance(self, book: Path):
        from data_modules.continuity_check import check_name_conflicts

        report = check_name_conflicts(book, name="苏小自")

        assert report["ok"] is True
        names = [c["name"] for c in report["conflicts"]]
        assert "苏小白" in names, "编辑距离 1 的撞名被报出"
        assert report["conflicts"][0]["distance"] == 1

    def test_alias_conflict_flagged(self, book: Path):
        from data_modules.continuity_check import check_name_conflicts

        report = check_name_conflicts(book, name="小白兔")

        assert any(c["name"] == "小白" for c in report["conflicts"]), "别名包含关系撞名"

    def test_distinct_name_passes(self, book: Path):
        from data_modules.continuity_check import check_name_conflicts

        report = check_name_conflicts(book, name="王铁柱")

        assert report["conflicts"] == []

    def test_exact_match_flagged_strongest(self, book: Path):
        from data_modules.continuity_check import check_name_conflicts

        report = check_name_conflicts(book, name="苏小白")

        assert report["conflicts"] and report["conflicts"][0]["distance"] == 0

    def test_cli_name_check(self, book: Path, capsys):
        from data_modules.continuity_check import main

        assert main(["--name", "苏小自", "--project-root", str(book), "--format", "json"]) == 0
        import json

        payload = json.loads(capsys.readouterr().out)
        assert payload["conflicts"] and payload["conflicts"][0]["name"] == "苏小白"
