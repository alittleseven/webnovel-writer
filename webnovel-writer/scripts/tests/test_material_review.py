#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T14（M2）material-review 测试。

对应方案：07 F-06（素材卷审：统计→建议→裁决执行）、06 §7（状态衰减）、08 T14。
契约：脚本统计 0 token（使用率/最近使用章/来源分布/衰减标记）；衰减=N 卷未用
（章→卷换算优先取 book.yaml 卷规模）；裁决执行 archive/delete/merge + journal；
LLM 建议在会话侧，CLI 只出确定性候选。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.domain_contract import init_domain_skeleton
    from data_modules.material_store import append_entries
    from data_modules.material_usage import append_usage

    init_domain_skeleton(tmp_path)
    (tmp_path / "book.yaml").write_text('spec_version: "7.0"\n卷规模: 40\n', encoding="utf-8")
    append_entries(tmp_path, "桥段", [
        {"id": "TR-001", "名称": "退婚三年之约", "核心摘要": "摘要"},
        {"id": "TR-002", "名称": "火葬场重逢", "核心摘要": "摘要"},
        {"id": "TR-003", "名称": "退婚三年之约", "核心摘要": "重名条目"},
        {"id": "TR-004", "名称": "当众对赌", "核心摘要": "摘要"},
    ], source="播种:玄幻")
    append_entries(tmp_path, "台词金句", [{"id": "GJ-001", "名称": "纸比人命贵"}], source="作者手写")
    # TR-001/002 在卷一用过（章 30/45），TR-004 从未用，GJ-001 卷二用过（章 88）
    append_usage(tmp_path, 30, [{"条目id": "TR-001", "定版版本": "live", "用法": "章纲引用"}])
    append_usage(tmp_path, 45, [{"条目id": "TR-002", "定版版本": "live", "用法": "章纲引用"}])
    append_usage(tmp_path, 88, [{"条目id": "GJ-001", "定版版本": "live", "用法": "正文复用"}])
    return tmp_path


class TestStats:
    def test_usage_counts_and_last_chapter(self, book: Path):
        from data_modules.material_review import review_stats

        report = review_stats(book)
        by_id = {(s["table"], s["id"]): s for s in report["entries"]}

        assert by_id[("桥段", "TR-001")]["uses"] == 1
        assert by_id[("桥段", "TR-001")]["last_chapter"] == 30
        assert by_id[("台词金句", "GJ-001")]["last_chapter"] == 88
        assert by_id[("桥段", "TR-004")]["uses"] == 0
        assert by_id[("桥段", "TR-004")]["last_chapter"] is None

    def test_source_distribution(self, book: Path):
        from data_modules.material_review import review_stats

        report = review_stats(book)

        assert report["source_distribution"] == {"播种:玄幻": 4, "作者手写": 1}

    def test_decay_marks_n_volumes_unused(self, book: Path):
        from data_modules.material_review import review_stats

        # book.yaml 卷规模=40：卷一=1-40 章，卷二=41-80，卷三=81+
        report = review_stats(book, current_volume=3, decay_volumes=1)
        by_id = {(s["table"], s["id"]): s for s in report["entries"]}

        assert by_id[("桥段", "TR-001")]["decayed"] is True, "最后用于卷一（章30），卷三审视已隔 2 卷"
        assert by_id[("桥段", "TR-002")]["decayed"] is True, "最后用章45 属卷二，隔 1 卷"
        assert by_id[("台词金句", "GJ-001")]["decayed"] is False, "章88 属卷三（当前卷）"
        assert by_id[("桥段", "TR-004")]["decayed"] is True, "从未使用且已过卷"

    def test_no_volume_no_decay(self, book: Path):
        from data_modules.material_review import review_stats

        report = review_stats(book)

        assert all(s["decayed"] is False for s in report["entries"])

    def test_merge_candidates_same_name_same_table(self, book: Path):
        from data_modules.material_review import review_candidates

        report = review_candidates(book)

        pairs = [(c["table"], c["ids"]) for c in report["merge_candidates"]]
        assert ("桥段", ["TR-001", "TR-003"]) in pairs


class TestApplyRulings:
    def test_archive_ruling(self, book: Path):
        from data_modules.author_journal import read_journal
        from data_modules.material_review import apply_rulings
        from data_modules.material_store import read_table

        report = apply_rulings(book, rulings=[{"table": "桥段", "id": "TR-001", "action": "archive", "reason": "两卷未用"}])

        assert report["ok"] is True and report["applied"] == 1
        rows = {r["id"]: r for r in read_table(book, "桥段", include_archived=True)}
        assert rows["TR-001"]["状态"] == "归档"
        assert "两卷未用" in rows["TR-001"]["备注"]
        assert any(e["domain"] == "素材" and "裁决" in str(e.get("summary")) for e in read_journal(book))

    def test_delete_ruling(self, book: Path):
        from data_modules.material_review import apply_rulings
        from data_modules.material_store import read_table

        apply_rulings(book, rulings=[{"table": "桥段", "id": "TR-003", "action": "delete"}])

        assert [r["id"] for r in read_table(book, "桥段", include_archived=True)] == ["TR-001", "TR-002", "TR-004"]

    def test_merge_ruling_updates_both_rows(self, book: Path):
        from data_modules.material_review import apply_rulings
        from data_modules.material_store import read_table

        apply_rulings(book, rulings=[{"table": "桥段", "id": "TR-003", "action": "merge", "merge_into": "TR-001"}])

        rows = {r["id"]: r for r in read_table(book, "桥段", include_archived=True)}
        assert rows["TR-003"]["状态"] == "归档"
        assert "并入:TR-001" in rows["TR-003"]["备注"]
        assert "并入自:TR-003" in rows["TR-001"]["备注"]

    def test_invalid_action_rejected(self, book: Path):
        from data_modules.material_review import apply_rulings

        report = apply_rulings(book, rulings=[{"table": "桥段", "id": "TR-001", "action": "炸掉"}])

        assert report["ok"] is False
        assert report["error"] == "invalid_action"

    def test_missing_id_reported(self, book: Path):
        from data_modules.material_review import apply_rulings

        report = apply_rulings(book, rulings=[{"table": "桥段", "id": "TR-999", "action": "archive"}])

        assert report["ok"] is True
        assert report["applied"] == 0
        assert report["missing"] == ["桥段:TR-999"]


class TestCLI:
    def test_cli_review_text(self, book: Path, capsys):
        from data_modules.material_store import main

        code = main(["review", "--volume", "3", "--project-root", str(book)])
        out = capsys.readouterr().out

        assert code == 0
        assert "TR-001" in out and "衰减" in out

    def test_cli_review_json(self, book: Path, capsys):
        from data_modules.material_store import main

        main(["review", "--volume", "3", "--project-root", str(book), "--format", "json"])
        payload = json.loads(capsys.readouterr().out)

        assert payload["ok"] is True
        assert len(payload["entries"]) == 5

    def test_cli_apply_ruling_string_form(self, book: Path, capsys):
        from data_modules.material_store import main
        from data_modules.material_store import read_table

        code = main(["apply-ruling", "--ruling", "桥段:TR-001:archive:两卷未用", "--project-root", str(book)])
        out = capsys.readouterr().out

        assert code == 0
        assert "TR-001" in out
        rows = {r["id"]: r for r in read_table(book, "桥段", include_archived=True)}
        assert rows["TR-001"]["状态"] == "归档"
