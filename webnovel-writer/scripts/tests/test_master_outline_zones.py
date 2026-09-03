#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T6（M1）总纲三区结构与自动分区迁移测试。

对应方案：05 §2.1（三区约定）、07 F-02（总纲分阶段管理）、08 T6。
契约：书级主体原样保留 + 三区增量追加（A 已写卷冻结/B 当前卷活跃/C 未来卷锚点）；
卷分类按定稿正文完成度（全写完=已写/部分=活跃/未动=锚点）；迁移幂等。
"""

from __future__ import annotations

from pathlib import Path

import pytest

VOLUME_PLAN_SECTION = """## 卷划分
| 卷号 | 卷名 | 章节范围 | 核心冲突 | 卷末高潮 |
|------|------|----------|----------|----------|
| 1 | 废墟求生 | 第1-80章 | 天灾爆发、觉醒 | 吃下第一场大灾 |
| 2 | 建城立基 | 第81-160章 | 种田建城 | 打退联军 |
| 3 | 割据博弈 | 第161-240章 | 多域势力 | 伪善翻车 |
"""

BOOK_LEVEL = """# 总纲

## 故事一句话
测试书一句话。

## 创意约束
- 约束一。

"""


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.domain_contract import init_domain_skeleton

    init_domain_skeleton(tmp_path)
    (tmp_path / "大纲" / "总纲.md").write_text(BOOK_LEVEL + VOLUME_PLAN_SECTION, encoding="utf-8", newline="\n")
    return tmp_path


def _write_chapters(root: Path, numbers: list[int]) -> None:
    for n in numbers:
        (root / "定稿" / "正文").mkdir(parents=True, exist_ok=True)
        (root / "定稿" / "正文" / f"{n:04d}-测试章.md").write_text(f"# {n}\n\n正文。", encoding="utf-8")


class TestVolumePlanParsing:
    def test_extract_volume_rows(self, book: Path):
        from data_modules.master_outline_zones import extract_volume_plan_rows

        rows = extract_volume_plan_rows((book / "大纲" / "总纲.md").read_text(encoding="utf-8"))

        assert len(rows) == 3
        assert rows[0]["卷号"] == "1"
        assert rows[0]["卷名"] == "废墟求生"
        assert rows[0]["章节范围"] == "第1-80章"
        assert rows[1]["卷末高潮"] == "打退联军"

    def test_missing_section_returns_empty(self):
        from data_modules.master_outline_zones import extract_volume_plan_rows

        assert extract_volume_plan_rows("# 总纲\n没有卷划分。\n") == []


class TestClassification:
    def test_partial_first_volume_is_active(self, book: Path):
        _write_chapters(book, [1, 2, 3])  # 卷 1（1-80）部分完成
        from data_modules.master_outline_zones import migrate_to_zones

        report = migrate_to_zones(book)

        assert report["classification"]["1"] == "active"
        assert report["classification"]["2"] == "anchor"
        assert report["classification"]["3"] == "anchor"
        assert report["written_volumes"] == []

    def test_full_volume_is_written(self, book: Path):
        _write_chapters(book, list(range(1, 81)))  # 卷 1 全写完
        _write_chapters(book, [81, 82])  # 卷 2 部分
        from data_modules.master_outline_zones import migrate_to_zones

        report = migrate_to_zones(book)

        assert report["classification"]["1"] == "written"
        assert report["classification"]["2"] == "active"
        assert report["written_volumes"] == ["1"]

    def test_no_chapters_all_anchor_first_active(self, book: Path):
        from data_modules.master_outline_zones import migrate_to_zones

        report = migrate_to_zones(book)

        assert report["classification"]["1"] == "active"
        assert report["classification"]["2"] == "anchor"


class TestMigration:
    def test_migrate_appends_three_zones(self, book: Path):
        from data_modules.master_outline_zones import has_zones, migrate_to_zones

        migrate_to_zones(book)
        text = (book / "大纲" / "总纲.md").read_text(encoding="utf-8")

        assert has_zones(text) is True
        assert "## 甲区 · 已写卷详案（冻结区）" in text
        assert "## 乙区 · 当前卷活跃区" in text
        assert "## 丙区 · 未来卷锚点" in text

    def test_book_level_body_preserved_verbatim(self, book: Path):
        from data_modules.master_outline_zones import migrate_to_zones

        original = (book / "大纲" / "总纲.md").read_text(encoding="utf-8")
        migrate_to_zones(book)
        text = (book / "大纲" / "总纲.md").read_text(encoding="utf-8")

        assert text.startswith(original.rstrip("\n")), "书级主体必须原样保留（红线）"

    def test_idempotent_second_migration(self, book: Path):
        from data_modules.master_outline_zones import migrate_to_zones

        first = migrate_to_zones(book)
        after_first = (book / "大纲" / "总纲.md").read_text(encoding="utf-8")
        second = migrate_to_zones(book)

        assert second["migrated"] is False
        assert (book / "大纲" / "总纲.md").read_text(encoding="utf-8") == after_first
        assert first["migrated"] is True

    def test_dry_run_does_not_write(self, book: Path):
        from data_modules.master_outline_zones import migrate_to_zones

        original = (book / "大纲" / "总纲.md").read_text(encoding="utf-8")
        report = migrate_to_zones(book, dry_run=True)

        assert report["migrated"] is True
        assert (book / "大纲" / "总纲.md").read_text(encoding="utf-8") == original

    def test_active_zone_points_to_volume_outline(self, book: Path):
        _write_chapters(book, [1])
        (book / "大纲" / "卷纲").mkdir(parents=True, exist_ok=True)
        (book / "大纲" / "卷纲" / "第01卷.md").write_text("# 第 1 卷\n", encoding="utf-8")
        from data_modules.master_outline_zones import migrate_to_zones

        migrate_to_zones(book)
        text = (book / "大纲" / "总纲.md").read_text(encoding="utf-8")

        assert "卷纲/第01卷.md" in text

    def test_anchor_zone_one_line_per_volume(self, book: Path):
        from data_modules.master_outline_zones import migrate_to_zones, parse_zones

        migrate_to_zones(book)
        zones = parse_zones((book / "大纲" / "总纲.md").read_text(encoding="utf-8"))

        anchor_lines = [ln for ln in zones["zone_c"].splitlines() if ln.strip().startswith("- ")]
        assert len(anchor_lines) == 2, "卷 2/3 各一行锚点（每卷 ≤10 行约定）"

    def test_written_zone_lists_volume_with_frozen_marker(self, book: Path):
        _write_chapters(book, list(range(1, 81)))
        (book / "大纲" / "卷纲").mkdir(parents=True, exist_ok=True)
        (book / "大纲" / "卷纲" / "第01卷.md").write_text("# 第 1 卷\n", encoding="utf-8")
        from data_modules.master_outline_zones import migrate_to_zones, parse_zones

        migrate_to_zones(book)
        zones = parse_zones((book / "大纲" / "总纲.md").read_text(encoding="utf-8"))

        assert "卷 1" in zones["zone_a"]
        assert "冻结" in zones["zone_a"]


class TestParseAndState:
    def test_parse_legacy_returns_none(self, book: Path):
        from data_modules.master_outline_zones import parse_zones

        assert parse_zones((book / "大纲" / "总纲.md").read_text(encoding="utf-8")) is None

    def test_zone_state_reports_active_volume(self, book: Path):
        _write_chapters(book, [1, 2])
        from data_modules.master_outline_zones import migrate_to_zones, zone_state

        migrate_to_zones(book)
        state = zone_state(book)

        assert state["has_zones"] is True
        assert state["active_volume"] == "1"
        assert state["written_volumes"] == []
