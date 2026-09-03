#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T7（M1）regen 画廊测试。

对应方案：07 F-02/F-04、08 T7、D3（画廊上限 3 版）、D7（current 指针）。
契约：版本存画廊永不覆盖目标；adopt 写回目标文件 + journal 留痕 + current 指针；
超上限需显式覆盖。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.domain_contract import init_domain_skeleton

    init_domain_skeleton(tmp_path)
    (tmp_path / "大纲" / "总纲.md").write_text("# 总纲\n当前生效版。\n", encoding="utf-8", newline="\n")
    return tmp_path


class TestSaveList:
    def test_save_version_appends_never_overwrites(self, book: Path):
        from data_modules.regen_gallery import list_versions, save_version

        r1 = save_version(book, domain="总纲", key="", content="# v1 提案\n甲案。\n")
        r2 = save_version(book, domain="总纲", key="", content="# v2 提案\n乙案。\n")

        assert r1["version"] == 1 and r2["version"] == 2
        versions = list_versions(book, domain="总纲", key="")
        assert len(versions) == 2

    def test_chapter_gallery_separate_per_chapter(self, book: Path):
        from data_modules.regen_gallery import list_versions, save_version

        save_version(book, domain="章纲", key="0039", content="# 39 稿 A")
        save_version(book, domain="章纲", key="0040", content="# 40 稿 A")

        assert len(list_versions(book, domain="章纲", key="0039")) == 1
        assert len(list_versions(book, domain="章纲", key="0040")) == 1


class TestMaxVersions:
    def test_fourth_save_requires_override(self, book: Path):
        from data_modules.regen_gallery import save_version

        for i in range(3):
            save_version(book, domain="总纲", key="", content=f"# v{i+1}")

        report = save_version(book, domain="总纲", key="", content="# v4")
        assert report["ok"] is False
        assert report["error"] == "max_versions"

        report = save_version(book, domain="总纲", key="", content="# v4", force=True)
        assert report["ok"] is True
        assert report["version"] == 4


class TestAdopt:
    def test_adopt_writes_target_and_leaves_trail(self, book: Path):
        from data_modules.author_journal import read_journal
        from data_modules.regen_gallery import adopt_version, save_version

        save_version(book, domain="总纲", key="", content="# 采纳版总纲\n新方案。\n")
        report = adopt_version(book, domain="总纲", key="", version=1)

        assert report["ok"] is True
        assert (book / "大纲" / "总纲.md").read_text(encoding="utf-8") == "# 采纳版总纲\n新方案。\n"

        actions = [e["action"] for e in read_journal(book)]
        assert "adopt" in actions

    def test_adopt_sets_current_pointer(self, book: Path):
        from data_modules.regen_gallery import adopt_version, read_current, save_version

        save_version(book, domain="总纲", key="", content="# A")
        adopt_version(book, domain="总纲", key="", version=1)

        assert read_current(book, domain="总纲", key="") == 1

    def test_adopt_chapter_writes_chapter_file(self, book: Path):
        from data_modules.regen_gallery import adopt_version, save_version

        save_version(book, domain="章纲", key="0039", content="# 第 39 章\n采纳稿。\n")
        report = adopt_version(book, domain="章纲", key="0039", version=1)

        assert report["ok"] is True
        assert (book / "大纲" / "章纲" / "0039.md").read_text(encoding="utf-8") == "# 第 39 章\n采纳稿。\n"

    def test_adopt_missing_version_fails(self, book: Path):
        from data_modules.regen_gallery import adopt_version

        report = adopt_version(book, domain="总纲", key="", version=9)
        assert report["ok"] is False


class TestDiffAndDiscard:
    def test_diff_two_versions(self, book: Path):
        from data_modules.regen_gallery import diff_versions, save_version

        save_version(book, domain="总纲", key="", content="# 总纲\n旧案。\n")
        save_version(book, domain="总纲", key="", content="# 总纲\n新案。\n")

        text = diff_versions(book, domain="总纲", key="", a=1, b=2)
        assert "-旧案。" in text
        assert "+新案。" in text

    def test_discard_removes_version(self, book: Path):
        from data_modules.regen_gallery import discard_version, list_versions, save_version

        save_version(book, domain="总纲", key="", content="# A")
        report = discard_version(book, domain="总纲", key="", version=1)

        assert report["ok"] is True
        assert list_versions(book, domain="总纲", key="") == []

    def test_discard_records_journal(self, book: Path):
        from data_modules.author_journal import read_journal
        from data_modules.regen_gallery import discard_version, save_version

        save_version(book, domain="总纲", key="", content="# A")
        discard_version(book, domain="总纲", key="", version=1)

        actions = [e["action"] for e in read_journal(book)]
        assert "discard" in actions
