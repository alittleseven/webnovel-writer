#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T15（M3）文风域测试。

对应方案：05 §1 文风域（宪法/金句库/指纹）、05 §3 迁移映射、06 §6 style_profile、
07 F-05（金句=素材自喂入口）、08 T15。
契约：宪法.md 从既有 风格契约.md 平移（不覆盖既有宪法）；指纹脚本可算、确定性稳定
（06 §6 全字段）；金句库标记 → 台词金句素材表自喂（来源=作者手写）。
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.domain_contract import init_domain_skeleton

    init_domain_skeleton(tmp_path)
    (tmp_path / "文风").mkdir(exist_ok=True)
    return tmp_path


def _write_chapter(root: Path, chapter: int, title: str, body: str, volume: int = 1) -> Path:
    path = root / "定稿" / "正文" / f"{chapter:04d}-{title}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"---\n章号: {chapter}\n标题: {title}\n卷: {volume}\n字数: 100\n---\n# 第{chapter}章 {title}\n\n{body}\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


CHAPTER_BODY = (
    "凌晨五点半，苏小白从便利店后门出来，脖子上还挂着没摘的工牌。\n"
    "\n"
    "早班的人没来。夜班经理隔着门喊了一嗓子：「小白，路上小心啊。」\n"
    "\n"
    "他没有回头。倒是街对面的高楼又裂开一道缝，灰尘像下雨一样落下来。\n"
    "\n"
    "「倒是挺准时。」他嘀咕了一句，把工牌塞进兜里，朝着灾雾最浓的方向走去。\n"
)


class TestConstitutionMigration:
    def test_migrate_moves_style_contract(self, book: Path):
        from data_modules.style_domain import migrate_constitution

        source = book / "设定集" / "风格契约.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# 风格契约\n- 短句为主\n", encoding="utf-8")

        report = migrate_constitution(book)

        assert report["ok"] is True
        assert report["migrated"] is True
        constitution = book / "文风" / "宪法.md"
        assert constitution.is_file()
        assert "短句为主" in constitution.read_text(encoding="utf-8")
        assert not source.exists(), "迁移=平移：原位置退役"

    def test_migrate_never_overwrites_existing_constitution(self, book: Path):
        from data_modules.style_domain import migrate_constitution

        source = book / "设定集" / "风格契约.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# 新契约\n", encoding="utf-8")
        constitution = book / "文风" / "宪法.md"
        constitution.write_text("# 作者手改的宪法\n", encoding="utf-8")

        report = migrate_constitution(book)

        assert report["ok"] is True
        assert report["migrated"] is False
        assert "作者手改" in constitution.read_text(encoding="utf-8")

    def test_migrate_without_source_reports_clean(self, book: Path):
        from data_modules.style_domain import migrate_constitution

        report = migrate_constitution(book)

        assert report["ok"] is True
        assert report["migrated"] is False
        assert report["reason"] == "no_source"


class TestFingerprint:
    def test_compute_and_write_all_fields(self, book: Path):
        from data_modules.style_domain import fingerprint_path, read_fingerprint, write_fingerprint_from_book

        _write_chapter(book, 1, "天裂", CHAPTER_BODY)
        _write_chapter(book, 2, "想活", CHAPTER_BODY)

        report = write_fingerprint_from_book(book)

        assert report["ok"] is True
        assert report["chapters"] == 2
        fp = read_fingerprint(book)
        assert fingerprint_path(book).is_file()
        for key in ("句长", "段落", "对话占比", "said_tag_ratio", "高频口头禅", "标点"):
            assert key in fp, f"06 §6 字段缺失: {key}"
        assert 0.0 < fp["对话占比"] < 1.0
        assert fp["金句样本"] == []

    def test_fingerprint_deterministic(self, book: Path):
        from data_modules.style_domain import read_fingerprint, write_fingerprint_from_book

        _write_chapter(book, 1, "天裂", CHAPTER_BODY)
        write_fingerprint_from_book(book)
        first = read_fingerprint(book)
        write_fingerprint_from_book(book)
        second = read_fingerprint(book)

        assert first == second, "同一定稿两次计算必须逐字段一致（T15 验收：稳定）"

    def test_single_chapter_increment(self, book: Path):
        from data_modules.style_domain import write_fingerprint_from_book

        _write_chapter(book, 1, "天裂", CHAPTER_BODY)
        _write_chapter(book, 2, "想活", CHAPTER_BODY)
        report = write_fingerprint_from_book(book, chapters=[2])

        assert report["ok"] is True
        assert report["chapters"] == 1

    def test_empty_book_reports_zero(self, book: Path):
        from data_modules.style_domain import write_fingerprint_from_book

        report = write_fingerprint_from_book(book)

        assert report["ok"] is True
        assert report["chapters"] == 0

    def test_golden_sentences_linked_into_fingerprint(self, book: Path):
        from data_modules.style_domain import add_golden, read_fingerprint, write_fingerprint_from_book

        _write_chapter(book, 37, "纸债", CHAPTER_BODY)
        add_golden(book, chapter=37, text="纸比人命贵。")
        write_fingerprint_from_book(book)

        fp = read_fingerprint(book)
        assert fp["金句样本"] == [{"章": 37, "摘录": "纸比人命贵。"}]


class TestGoldenLibrary:
    def test_add_golden_assigns_ids(self, book: Path):
        from data_modules.author_journal import read_journal
        from data_modules.style_domain import add_golden, list_goldens

        first = add_golden(book, chapter=37, text="纸比人命贵。")
        second = add_golden(book, chapter=38, text="灾是最公平的东西。", note="卷一收尾")

        assert first["ok"] and second["ok"]
        assert first["id"] == "G-001" and second["id"] == "G-002"
        entries = list_goldens(book)
        assert [e["id"] for e in entries] == ["G-001", "G-002"]
        assert any(e["action"] == "learn" and e["domain"] == "文风" for e in read_journal(book))

    def test_feed_golden_into_material_table(self, book: Path):
        from data_modules.material_store import read_table
        from data_modules.style_domain import add_golden, feed_golden

        add_golden(book, chapter=37, text="纸比人命贵。")
        report = feed_golden(book, golden_id="G-001")

        assert report["ok"] is True
        rows = read_table(book, "台词金句")
        assert rows[0]["id"] == "G-001"
        assert rows[0]["名称"] == "纸比人命贵。"
        assert rows[0]["来源"] == "作者手写", "素材自喂入口：来源标记正确"

    def test_feed_twice_skips_duplicate(self, book: Path):
        from data_modules.style_domain import add_golden, feed_golden

        add_golden(book, chapter=37, text="纸比人命贵。")
        feed_golden(book, golden_id="G-001")
        report = feed_golden(book, golden_id="G-001")

        assert report["ok"] is False
        assert report["error"] == "duplicate_id"

    def test_feed_missing_golden(self, book: Path):
        from data_modules.style_domain import feed_golden

        report = feed_golden(book, golden_id="G-999")
        assert report["ok"] is False
        assert report["error"] == "golden_missing"


class TestCLI:
    def test_cli_fingerprint_and_golden(self, book: Path, capsys):
        from data_modules.style_domain import main

        _write_chapter(book, 1, "天裂", CHAPTER_BODY)
        assert main(["fingerprint", "--project-root", str(book)]) == 0
        assert main(["golden-add", "--chapter", "1", "--text", "纸比人命贵。", "--project-root", str(book)]) == 0
        assert main(["golden-list", "--project-root", str(book)]) == 0
        assert main(["golden-feed", "--id", "G-001", "--project-root", str(book)]) == 0
        out = capsys.readouterr().out
        assert "G-001" in out
