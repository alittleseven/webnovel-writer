#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T16（M3）author_model 测试。

对应方案：06 §5（author_model.md 项目层 + 跨书偏好.yaml 用户层）、07 F-12（学习闭环：
learn --from-journal 卷级归纳 → 建议作者确认 → 双层回写 → 进 context 装配）、08 T16。
契约：脚本统计 0 token；建议文件作者确认后才 apply（绝不自动改 author_model.md）；
跨书偏好 审稿习惯.接受AI建议率 由 journal adopt/discard 统计维护。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.author_journal import append_events
    from data_modules.domain_contract import init_domain_skeleton

    init_domain_skeleton(tmp_path)
    (tmp_path / "book.yaml").write_text('spec_version: "7.0"\n卷规模: 40\n', encoding="utf-8")
    append_events(
        tmp_path,
        [
            {  # 卷一章纲编辑（ins 12）
                "actor": "author", "action": "edit", "domain": "章纲",
                "path": "大纲/章纲/0001.md", "change_kind": "content",
                "diff_stat": {"ins": 12, "del": 4}, "summary": "把对峙提前", "impact": [],
            },
            {  # 卷二正文修改（del 为主 → 雷点候选）
                "actor": "author", "action": "edit", "domain": "正文",
                "path": "定稿/正文/0045-x.md", "change_kind": "delete",
                "diff_stat": {"ins": 0, "del": 30}, "summary": "删掉心中暗道套话", "impact": [],
            },
            {  # 素材采纳
                "actor": "author", "action": "adopt", "domain": "素材",
                "path": "素材/regen/ai-v1.csv", "change_kind": "structure",
                "diff_stat": {"ins": 2, "del": 0}, "summary": "采纳候选", "impact": [],
            },
            {  # 画廊丢弃 ×2
                "actor": "author", "action": "discard", "domain": "素材",
                "path": "素材/regen/ai-v2.csv", "change_kind": "structure",
                "diff_stat": {"ins": 0, "del": 0}, "summary": "丢弃候选", "impact": [],
            },
            {
                "actor": "author", "action": "discard", "domain": "素材",
                "path": "素材/regen/chaishu-v1.csv", "change_kind": "structure",
                "diff_stat": {"ins": 0, "del": 0}, "summary": "丢弃候选", "impact": [],
            },
        ],
    )
    return tmp_path


class TestLearnFromJournal:
    def test_learn_generates_suggestion_with_stats(self, book: Path):
        from data_modules.author_model import learn_from_journal

        report = learn_from_journal(book)

        assert report["ok"] is True
        assert report["events_in_scope"] == 5
        suggestion_path = book / "作者" / "author_model-建议.md"
        assert suggestion_path.is_file()
        text = suggestion_path.read_text(encoding="utf-8")
        for section in ("节奏偏好", "雷点", "修改习惯", "当前书特定要求"):
            assert section in text, "建议文件含 06 §5 四段骨架"
        assert "心中暗道" in text, "删除型修改进雷点候选"

    def test_learn_volume_filter(self, book: Path):
        from data_modules.author_model import learn_from_journal

        report = learn_from_journal(book, volume=1)

        assert report["ok"] is True
        assert report["events_in_scope"] == 1, "卷规模 40：仅第 1 章事件属卷一"
        text = (book / "作者" / "author_model-建议.md").read_text(encoding="utf-8")
        assert "0001" in text

    def test_learn_empty_journal_still_ok(self, tmp_path: Path):
        from data_modules.domain_contract import init_domain_skeleton
        from data_modules.author_model import learn_from_journal

        init_domain_skeleton(tmp_path)
        report = learn_from_journal(tmp_path)

        assert report["ok"] is True
        assert report["events_in_scope"] == 0


class TestApplySuggestion:
    def test_apply_creates_model_with_confirmed_section(self, book: Path):
        from data_modules.author_journal import read_journal
        from data_modules.author_model import apply_suggestion, learn_from_journal

        learn_from_journal(book)
        report = apply_suggestion(book)

        assert report["ok"] is True
        model = book / "作者" / "author_model.md"
        assert model.is_file()
        text = model.read_text(encoding="utf-8")
        assert "已确认" in text
        assert any(e["action"] == "learn" and "确认" in str(e.get("summary")) for e in read_journal(book))

    def test_apply_appends_second_round(self, book: Path):
        from data_modules.author_model import apply_suggestion, learn_from_journal

        learn_from_journal(book)
        apply_suggestion(book)
        learn_from_journal(book, volume=2)
        report = apply_suggestion(book)

        assert report["ok"] is True
        text = (book / "作者" / "author_model.md").read_text(encoding="utf-8")
        assert text.count("已确认") == 2

    def test_apply_without_suggestion_fails_clean(self, book: Path):
        from data_modules.author_model import apply_suggestion

        report = apply_suggestion(book)
        assert report["ok"] is False
        assert report["error"] == "suggestion_missing"


class TestCrossBookPreferences:
    def test_apply_updates_acceptance_rate(self, book: Path):
        from data_modules.author_model import apply_suggestion, learn_from_journal, read_preferences

        learn_from_journal(book)
        apply_suggestion(book)
        prefs = read_preferences(book)

        # journal: 1 adopt + 2 discard → 接受率 1/3
        assert prefs["审稿习惯"]["接受AI建议率"] == round(1 / 3, 2)
        assert prefs["审稿习惯"]["偏好裁决选项数"] == 3

    def test_apply_twice_recomputes_not_corrupts(self, book: Path):
        from data_modules.author_model import apply_suggestion, learn_from_journal, read_preferences

        learn_from_journal(book)
        apply_suggestion(book)
        apply_suggestion(book)

        prefs = read_preferences(book)
        assert prefs["审稿习惯"]["接受AI建议率"] == round(1 / 3, 2)


class TestContextSection:
    def test_load_author_model_section(self, book: Path):
        from data_modules.author_model import apply_suggestion, learn_from_journal, load_author_model_section

        learn_from_journal(book)
        apply_suggestion(book)
        section = load_author_model_section(book)

        assert section["模型要点"]
        assert section["跨书偏好"]
        assert "接受AI建议率" in section["跨书偏好"]

    def test_section_empty_when_absent(self, tmp_path: Path):
        from data_modules.author_model import load_author_model_section

        assert load_author_model_section(tmp_path) == {"模型要点": "", "跨书偏好": ""}


class TestCLI:
    def test_cli_learn_apply_show(self, book: Path, capsys):
        from data_modules.author_model import main

        assert main(["learn", "--from-journal", "--volume", "1", "--project-root", str(book)]) == 0
        assert main(["apply", "--project-root", str(book)]) == 0
        capsys.readouterr()  # 丢弃前两步输出，只校验 show 的 JSON
        assert main(["show", "--project-root", str(book), "--format", "json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert "模型要点" in payload and "跨书偏好" in payload
