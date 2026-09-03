#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T5（M0）impact 引用反查 v1 测试。

对应方案：docs/zcode/webnovel-copilot-300/07-feature-flows.md F-07、08 T5。
契约：路径 → 受影响面（章/资产）反查 + 三选项裁决建议；
章纲→章、定版素材→使用轨迹、战力锚点→战例账本、正文→事实复检。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.domain_contract import init_domain_skeleton

    init_domain_skeleton(tmp_path)
    return tmp_path


def _write(root: Path, rel: str, content: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


class TestChapterOutlineImpact:
    def test_outline_maps_to_chapter(self, book: Path):
        from data_modules.impact_analyzer import analyze_impact

        report = analyze_impact(book, "大纲/章纲/0039.md")

        assert report["domain"] == "章纲"
        assert report["chapter"] == "0039"
        assert "chapter:0039" in report["stale_targets"]
        assert any("context-stale" in i for i in report["impacts"])

    def test_outline_active_no_three_options(self, book: Path):
        # 章纲是 active 态：三选项裁决只属于定版（F-07），章纲只走 context-stale
        from data_modules.impact_analyzer import analyze_impact

        report = analyze_impact(book, "大纲/章纲/0040.md")

        assert report["options"] == []
        assert report["suggestions"], "章纲应有重编译建议"


class TestMaterialImpact:
    def test_definitive_material_reverse_lookup_via_usage_trail(self, book: Path):
        _write(
            book,
            "素材/使用轨迹.jsonl",
            "\n".join(
                [
                    json.dumps({"章": 35, "条目id": "TR-012", "定版版本": "v01", "用法": "打脸桥段"}, ensure_ascii=False),
                    json.dumps({"章": 38, "条目id": "TR-012", "定版版本": "v01", "用法": "打脸桥段"}, ensure_ascii=False),
                    json.dumps({"章": 36, "条目id": "SP-007", "定版版本": "v01", "用法": "码头夜战"}, ensure_ascii=False),
                ]
            ),
        )
        from data_modules.impact_analyzer import analyze_impact

        report = analyze_impact(book, "素材/定版/v01/桥段.csv")

        assert report["affected_chapters"] == [35, 38], "按使用轨迹反查引用章"
        assert report["stale_targets"] == ["material:素材/定版/v01/桥段.csv"]

    def test_missing_trail_returns_empty_not_crash(self, book: Path):
        from data_modules.impact_analyzer import analyze_impact

        report = analyze_impact(book, "素材/定版/v02/桥段.csv")

        assert report["affected_chapters"] == []
        assert report["ok"] is True

    def test_trail_table_prefix_filters_other_tables(self, book: Path):
        # 表级反查 = 版本 + 条目id 表前缀：TR-* 属桥段表命中；SP-*（场景写法）不混入
        _write(
            book,
            "素材/使用轨迹.jsonl",
            "\n".join(
                [
                    json.dumps({"章": 40, "条目id": "TR-999", "定版版本": "v01", "用法": ""}, ensure_ascii=False),
                    json.dumps({"章": 41, "条目id": "SP-001", "定版版本": "v01", "用法": ""}, ensure_ascii=False),
                ]
            ),
        )
        from data_modules.impact_analyzer import analyze_impact

        report = analyze_impact(book, "素材/定版/v01/桥段.csv")

        assert report["affected_chapters"] == [40]


class TestPowerAnchorImpact:
    def test_anchor_maps_to_battle_ledger_chapters(self, book: Path):
        _write(
            book,
            "设定/力量锚点.yaml",
            "\n".join(
                [
                    "spec: power-anchor/1",
                    "境界链:",
                    "  - {序: 1, 名: 聚气}",
                    "战例账本:",
                    "  - {章: 37, 对阵: A vs B, 结果: 胜, 跨阶: 1}",
                    "  - {章: 41, 对阵: C vs D, 结果: 负, 跨阶: 2}",
                ]
            ),
        )
        from data_modules.impact_analyzer import analyze_impact

        report = analyze_impact(book, "设定/力量锚点.yaml")

        assert report["domain"] == "战力"
        assert sorted(report["affected_chapters"]) == [37, 41]
        assert "power-anchor" in report["stale_targets"]

    def test_malformed_anchor_yaml_degrades(self, book: Path):
        _write(book, "设定/力量锚点.yaml", "这不是: [合法 yaml")  # 故意不对称

        from data_modules.impact_analyzer import analyze_impact

        report = analyze_impact(book, "设定/力量锚点.yaml")
        assert report["affected_chapters"] == []
        assert report["ok"] is True


class TextMainTextImpact:
    pass


class TestMainTextImpact:
    def test_chapter_text_impact(self, book: Path):
        from data_modules.impact_analyzer import analyze_impact

        report = analyze_impact(book, "定稿/正文/0037-暗纸.md")

        assert report["domain"] == "正文"
        assert report["chapter"] == "0037"
        assert any("fact-recheck" in i for i in report["impacts"])
        assert any("摘要" in s or "summary" in s for s in report["suggestions"])


class TestUnknownDomain:
    def test_other_domain_minimal_report(self, book: Path):
        from data_modules.impact_analyzer import analyze_impact

        report = analyze_impact(book, "随便.md")

        assert report["domain"] == "其他"
        assert report["ok"] is True
        assert report["options"] == []
