#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T24（M5）多稿择优测试。

对应方案：03 R3（F-03）、08 T24、D0-4（默认 2 稿）。
契约：rubric 六维落库（缺维/越界拒绝）；choose 取均分最高稿并标 chosen，
均分 <3.5 按最弱项给定向重写提示（只提示一次）；审查分回填选中稿（校准对照）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

FULL = {"钩子强度": 4, "情绪弧": 4, "场景必要性": 4, "信息密度": 4, "对话声线区分": 4, "结尾未完感": 4}


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    from data_modules.config import DataModulesConfig

    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return tmp_path


class TestRecord:
    def test_record_and_report_roundtrip(self, root: Path):
        from data_modules.draft_selection import record_draft, report

        first = record_draft(root, chapter=39, draft_no=1, scores=FULL, rationale="结构完整")
        assert first["ok"] is True and first["total"] == 4.0

        rows = report(root, chapter=39)["drafts"]
        assert len(rows) == 1
        assert rows[0]["scores"]["钩子强度"] == 4
        assert rows[0]["rationale"] == "结构完整"

    def test_missing_dimension_rejected(self, root: Path):
        from data_modules.draft_selection import record_draft

        report = record_draft(root, chapter=39, draft_no=1, scores={"钩子强度": 4})

        assert report["ok"] is False
        assert report["error"] == "missing_dimensions"

    def test_score_out_of_range_rejected(self, root: Path):
        from data_modules.draft_selection import record_draft

        scores = {**FULL, "钩子强度": 6}
        report = record_draft(root, chapter=39, draft_no=1, scores=scores)

        assert report["ok"] is False
        assert report["error"] == "score_out_of_range"


class TestChoose:
    def test_choose_marks_highest_total(self, root: Path):
        from data_modules.draft_selection import choose_draft, record_draft

        record_draft(root, chapter=39, draft_no=1, scores=FULL)
        better = {dim: 5 for dim in FULL}
        better["信息密度"] = 4
        record_draft(root, chapter=39, draft_no=2, scores=better, rationale="密度更高")

        chosen = choose_draft(root, chapter=39)

        assert chosen["ok"] is True
        assert chosen["chosen_draft_no"] == 2
        assert chosen["drafts"] == 2
        assert "rewrite_hint" not in chosen

    def test_below_floor_returns_weakest_dimension_hint(self, root: Path):
        from data_modules.draft_selection import choose_draft, record_draft

        weak = {dim: 3 for dim in FULL}
        weak["对话声线区分"] = 2
        record_draft(root, chapter=40, draft_no=1, scores=weak)

        chosen = choose_draft(root, chapter=40)

        assert chosen["chosen_total"] < 3.5
        assert chosen["rewrite_hint"]["dimension"] == "对话声线区分"
        assert "最多 1 次" in chosen["rewrite_hint"]["note"]

    def test_rewrite_hint_given_once_only(self, root: Path):
        from data_modules.draft_selection import choose_draft, record_draft

        weak = {dim: 3 for dim in FULL}
        record_draft(root, chapter=41, draft_no=1, scores=weak)
        first = choose_draft(root, chapter=41)

        assert "rewrite_hint" in first, "低于阈值首选给出定向重写提示"

        # 重写后带标记重新登记 → 不再提示（最多 1 次）
        record_draft(root, chapter=41, draft_no=2, scores=weak, rationale="（rewrite_done）已按最弱项重写")
        second = choose_draft(root, chapter=41)

        assert "rewrite_hint" not in second

    def test_choose_without_drafts_fails_clean(self, root: Path):
        from data_modules.draft_selection import choose_draft

        assert choose_draft(root, chapter=99)["error"] == "no_drafts"


class TestLinkAndCLI:
    def test_link_review_score_backfills_chosen(self, root: Path):
        from data_modules.draft_selection import choose_draft, link_review_score, record_draft, report

        record_draft(root, chapter=39, draft_no=1, scores=FULL)
        record_draft(root, chapter=39, draft_no=2, scores={dim: 5 for dim in FULL})
        choose_draft(root, chapter=39)

        assert link_review_score(root, chapter=39, review_score=86)["ok"] is True
        rows = {r["draft_no"]: r for r in report(root, chapter=39)["drafts"]}
        assert rows[2]["review_score"] == 86
        assert rows[1]["review_score"] is None

    def test_cli_record_choose_link(self, root: Path, capsys):
        from data_modules.draft_selection import main

        scores = ",".join(f"{dim}:4" for dim in FULL)
        assert main(["record", "--chapter", "39", "--draft", "1", "--scores", scores, "--project-root", str(root)]) == 0
        assert main(["choose", "--chapter", "39", "--project-root", str(root)]) == 0
        capsys.readouterr()
        assert main(["link", "--chapter", "39", "--score", "88", "--project-root", str(root), "--format", "json"]) == 0
        out = capsys.readouterr().out
        assert '"review_score": 88.0' in out
