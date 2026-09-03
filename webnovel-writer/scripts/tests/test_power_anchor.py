#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T18（M4）力量锚点抽取测试。

对应方案：06 §8（力量锚点.yaml schema 与双层模型）、05 §3（锚点抽取器：半自动、
作者确认）、08 T18。
契约：从 力量体系.md 抽锚点候选（等级顺序行 + 每级核心能力）→ 作者 apply 确认
才写 设定/力量锚点.yaml（既有文件不覆盖）；境界链校验（序单调/名唯一）绿。
"""

from __future__ import annotations

from pathlib import Path

import pytest


POWER_MD = """# 力量体系设定

## 体系类型
- 体系类型：境界制（修真）
- 典型境界链（可选）：炼气 → 筑基 → 金丹 → 元婴

## 等级体系
- 等级顺序：炼气(1-9层) → 筑基 → 金丹 → 元婴
- 每级核心能力：
  - 炼气：引气入体、体质强化、简单术法
  - 筑基：道基铸成、御物御剑、寿命200
  - 金丹：金丹大成、法术质变、寿命500
  - 元婴：碎丹成婴、神识成形、寿命1000
"""


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.domain_contract import init_domain_skeleton

    init_domain_skeleton(tmp_path)
    settings = tmp_path / "定稿" / "设定"
    settings.mkdir(parents=True, exist_ok=True)
    (settings / "力量体系.md").write_text(POWER_MD, encoding="utf-8")
    return tmp_path


class TestExtract:
    def test_extract_candidates_in_order(self, book: Path):
        from data_modules.power_anchor import extract_candidates

        report = extract_candidates(book)

        assert report["ok"] is True
        names = [c["名"] for c in report["candidates"]]
        assert names == ["炼气", "筑基", "金丹", "元婴"], "按等级顺序行排序，括号层剥离"
        assert [c["序"] for c in report["candidates"]] == [1, 2, 3, 4]

    def test_extract_maps_descriptions_and_lifespan(self, book: Path):
        from data_modules.power_anchor import extract_candidates

        report = extract_candidates(book)
        by_name = {c["名"]: c for c in report["candidates"]}

        assert "引气入体" in by_name["炼气"]["差距描述"]
        assert by_name["筑基"]["寿元"] == "200"
        assert by_name["炼气"]["寿元"] == ""

    def test_extract_without_source_fails_clean(self, tmp_path: Path):
        from data_modules.domain_contract import init_domain_skeleton
        from data_modules.power_anchor import extract_candidates

        init_domain_skeleton(tmp_path)
        report = extract_candidates(tmp_path)

        assert report["ok"] is False
        assert report["error"] == "source_missing"


class TestApply:
    def test_apply_writes_anchor_file_with_defaults(self, book: Path):
        from data_modules.author_journal import read_journal
        from data_modules.power_anchor import anchor_path, apply_candidates, extract_candidates, load_anchor

        candidates = extract_candidates(book)["candidates"]
        report = apply_candidates(book, candidates)

        assert report["ok"] is True
        assert anchor_path(book).is_file()
        anchor = load_anchor(book)
        assert anchor["spec"] == "power-anchor/1"
        assert anchor["境界链"][0] == {"序": 1, "名": "炼气", "差距描述": "引气入体、体质强化、简单术法", "寿元": ""}
        assert anchor["越级规则"]["跨1阶"] == "需列依据（金手指/代价/外因 任一）", "06 §8 默认越级规则"
        assert anchor["战例账本"] == [] and anchor["通胀记录"] == []
        assert any(e["domain"] == "战力" for e in read_journal(book))

    def test_apply_refuses_existing_file(self, book: Path):
        from data_modules.power_anchor import anchor_path, apply_candidates, extract_candidates

        candidates = extract_candidates(book)["candidates"]
        apply_candidates(book, candidates)
        report = apply_candidates(book, candidates)

        assert report["ok"] is False
        assert report["error"] == "already_exists", "作者主权：既有锚点表不覆盖"


class TestValidate:
    def test_validate_green_on_applied_chain(self, book: Path):
        from data_modules.power_anchor import apply_candidates, extract_candidates, validate_chain

        apply_candidates(book, extract_candidates(book)["candidates"])

        assert validate_chain(book) == []

    def test_validate_detects_broken_order(self, book: Path):
        from data_modules.power_anchor import apply_candidates, load_anchor, validate_chain, write_anchor

        chain = [
            {"序": 1, "名": "炼气", "差距描述": "", "寿元": ""},
            {"序": 3, "名": "金丹", "差距描述": "", "寿元": ""},
        ]
        apply_candidates(book, [])
        write_anchor(book, {**load_anchor(book), "境界链": chain})

        problems = validate_chain(book)

        assert any("序" in p for p in problems)

    def test_validate_detects_duplicate_names(self, book: Path):
        from data_modules.power_anchor import apply_candidates, load_anchor, validate_chain, write_anchor

        chain = [
            {"序": 1, "名": "炼气", "差距描述": "", "寿元": ""},
            {"序": 2, "名": "炼气", "差距描述": "", "寿元": ""},
        ]
        apply_candidates(book, [])
        write_anchor(book, {**load_anchor(book), "境界链": chain})

        assert any("重名" in p for p in validate_chain(book))


class TestCLI:
    def test_cli_extract_and_validate(self, book: Path, capsys):
        from data_modules.power_anchor import main

        assert main(["extract", "--apply", "--project-root", str(book)]) == 0
        assert main(["validate", "--project-root", str(book), "--format", "json"]) == 0
        payload = capsys.readouterr().out.strip().split("\n")
        assert payload
