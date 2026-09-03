#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T19（M4）战例账本与 power_check 测试。

对应方案：06 §8（战例账本/通胀记录/校验语义）、07 F-09、08 T19。
契约：硬校验①跨阶依据完备性（跨1阶任一依据；跨2阶金手指+代价双列且卷纲预告）、
硬校验②与境界链矛盾（跨阶超出链长）；软校验③通胀偏差连续超阈值（medium 提示）；
硬问题 = high + blocking（无依据越级样章被阻断）；战例登记即账本回写（F-09④）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.power_anchor import apply_candidates

    from data_modules.domain_contract import init_domain_skeleton

    init_domain_skeleton(tmp_path)
    apply_candidates(
        tmp_path,
        [
            {"序": 1, "名": "炼气", "差距描述": "引气入体", "寿元": ""},
            {"序": 2, "名": "筑基", "差距描述": "道基铸成", "寿元": "200"},
            {"序": 3, "名": "金丹", "差距描述": "法术质变", "寿元": "500"},
        ],
    )
    return tmp_path


class TestBattleLedger:
    def test_record_battle_appends_and_journals(self, book: Path):
        from data_modules.author_journal import read_journal
        from data_modules.power_anchor import load_anchor, record_battle

        report = record_battle(
            book,
            chapter=37,
            matchup="苏小白 vs 赵姓汉子",
            result="胜",
            cross=1,
            basis={"代价": "折损纸人一具", "外因": "夜战"},
        )

        assert report["ok"] is True
        battles = load_anchor(book)["战例账本"]
        assert battles == [
            {
                "章": 37,
                "对阵": "苏小白 vs 赵姓汉子",
                "结果": "胜",
                "跨阶": 1,
                "预告": False,
                "依据": {"代价": "折损纸人一具", "外因": "夜战"},
            }
        ]
        assert any(e["domain"] == "战力" for e in read_journal(book))

    def test_record_duplicate_battle_refused(self, book: Path):
        from data_modules.power_anchor import record_battle

        record_battle(book, chapter=37, matchup="A vs B", result="胜", cross=0)
        report = record_battle(book, chapter=37, matchup="A vs B", result="胜", cross=0)

        assert report["ok"] is False
        assert report["error"] == "duplicate"


class TestPowerCheckHard:
    def test_cross_without_basis_is_high_blocking(self, book: Path):
        """T19 验收：越级无依据 → high issue 且 blocking（阻断）。"""
        from data_modules.power_anchor import power_check, record_battle

        record_battle(book, chapter=37, matchup="苏小白 vs 筑基武者", result="胜", cross=1, basis={})
        report = power_check(book)

        assert report["ok"] is False
        high = [i for i in report["issues"] if i["severity"] == "high"]
        assert high and high[0]["blocking"] is True
        assert "37" in high[0]["location"]
        assert "依据" in high[0]["description"]

    def test_cross_two_needs_golden_finger_plus_cost(self, book: Path):
        from data_modules.power_anchor import power_check, record_battle

        record_battle(
            book, chapter=41, matchup="A vs 金丹", result="胜", cross=2, basis={"金手指": "吃灾", "外因": "夜战"}
        )
        report = power_check(book)

        high = [i for i in report["issues"] if i["severity"] == "high"]
        assert any("代价" in i["description"] for i in high), "跨2阶缺代价双列 → high"

    def test_cross_two_without_outline_foreshadow_is_high(self, book: Path):
        from data_modules.power_anchor import power_check, record_battle

        record_battle(
            book,
            chapter=41,
            matchup="A vs 金丹",
            result="胜",
            cross=2,
            basis={"金手指": "吃灾", "代价": "灾痕加深"},
            foreshadowed=False,
        )
        report = power_check(book)

        high = [i for i in report["issues"] if i["severity"] == "high"]
        assert any("预告" in i["description"] for i in high), "跨2阶缺卷纲预告 → high"

    def test_compliant_cross_passes(self, book: Path):
        from data_modules.power_anchor import power_check, record_battle

        record_battle(
            book,
            chapter=37,
            matchup="苏小白 vs 筑基武者",
            result="胜",
            cross=1,
            basis={"外因": "夜战"},
            foreshadowed=True,
        )
        report = power_check(book)

        assert report["ok"] is True, report
        assert report["issues"] == []

    def test_cross_beyond_chain_length_is_contradiction(self, book: Path):
        from data_modules.power_anchor import power_check, record_battle

        record_battle(
            book,
            chapter=42,
            matchup="A vs 渡劫",
            result="胜",
            cross=6,
            basis={"金手指": "吃灾", "代价": "重伤"},
            foreshadowed=True,
        )
        report = power_check(book)

        high = [i for i in report["issues"] if i["severity"] == "high"]
        assert any("境界链" in i["description"] for i in high), "链长 3：跨6 阶为矛盾"


class TestPowerCheckSoft:
    def test_consecutive_inflation_beyond_threshold_warns(self, book: Path):
        from data_modules.power_anchor import power_check, record_inflation

        record_inflation(book, chapter=38, anchor_point="筑基(2)", event="突破", milestone="卷二末筑基", deviation="提前5章")
        record_inflation(book, chapter=39, anchor_point="筑基(3)", event="突破", milestone="卷三初筑基", deviation="提前4章")
        report = power_check(book)

        medium = [i for i in report["issues"] if i["severity"] == "medium"]
        assert medium and not medium[0]["blocking"], "连续超阈值为软提示"
        assert "通胀" in medium[0]["description"]

    def test_single_inflation_within_threshold_no_issue(self, book: Path):
        from data_modules.power_anchor import power_check, record_inflation

        record_inflation(book, chapter=38, anchor_point="筑基(2)", event="突破", milestone="卷二末筑基", deviation="提前2章")

        assert power_check(book)["issues"] == []


class TestCLI:
    def test_cli_battle_and_check(self, book: Path, capsys):
        from data_modules.power_anchor import main

        assert main(
            ["battle", "--chapter", "37", "--matchup", "A vs B", "--result", "胜", "--cross", "1", "--project-root", str(book)]
        ) == 0
        capsys.readouterr()  # 丢弃 battle 的 text 输出，只校验 check 的 JSON
        code = main(["check", "--project-root", str(book), "--format", "json"])
        payload = json.loads(capsys.readouterr().out)
        assert code != 0, "发现硬问题（无依据越级）时以非零退出码阻断"
        assert payload["issues"][0]["severity"] == "high"
