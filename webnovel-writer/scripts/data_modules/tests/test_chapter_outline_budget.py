#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chapter_outline_loader 预算测试（S4/C4 残留）：拆分章纲纳入预算 + plot_structure 限量。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from chapter_outline_loader import (  # noqa: E402
    load_chapter_outline,
    load_chapter_plot_structure,
)

SPLIT_MD = """# 第36章 放话

- 目标：消化新安城与熊哥的双重压力
- 阻力：熊哥放话「风暴过后再来」，据点人心又起波动

{desc}

CBN：苏小白 | 稳住 | 据点人心
CPNs：幸存者 | 议论 | 风暴与去留
CEN：苏小白 | 定调 | 自家的事自家做主
必须覆盖节点：CBN、CEN
本章禁区：不写新安城报复戏；熊哥不出场
"""


def _split_project(tmp_path: Path, body: str) -> Path:
    (tmp_path / "大纲").mkdir(parents=True, exist_ok=True)
    (tmp_path / "大纲" / "第36章-放话.md").write_text(
        SPLIT_MD.replace("{desc}", body), encoding="utf-8"
    )
    return tmp_path


class TestSplitOutlineBudget:
    def test_split_outline_within_budget_unchanged(self, tmp_path):
        project = _split_project(tmp_path, "短描述")

        text = load_chapter_outline(project, 36, max_chars=1500)

        assert text.startswith("# 第36章 放话")
        assert "短描述" in text
        assert "已按字段优先级截断" not in text

    def test_split_outline_over_budget_keeps_priority_fields(self, tmp_path):
        project = _split_project(tmp_path, "描" * 6000)

        text = load_chapter_outline(project, 36, max_chars=1500)

        assert len(text) < 2000  # 远小于 6000+ 的全文
        assert "CBN：苏小白 | 稳住 | 据点人心" in text  # 关键字段整行保留
        assert "本章禁区：不写新安城报复戏" in text
        assert "已按字段优先级截断" in text

    def test_split_outline_no_budget_returns_full(self, tmp_path):
        project = _split_project(tmp_path, "描" * 6000)

        text = load_chapter_outline(project, 36, max_chars=None)

        assert "描" * 50 in text  # 全文
        assert "已按字段优先级截断" not in text


class TestPlotStructureLimit:
    def test_parse_fields_survive_budget_truncation(self, tmp_path):
        project = _split_project(tmp_path, "描" * 6000)

        plot = load_chapter_plot_structure(project, 36)

        # 限量后字段解析不受影响（字段优先级截断保住标签行）
        assert plot.get("mandatory_nodes")
        assert plot.get("prohibitions")

    def test_explicit_max_chars_param(self, tmp_path):
        project = _split_project(tmp_path, "描" * 6000)

        plot = load_chapter_plot_structure(project, 36, max_chars=600)

        assert plot.get("mandatory_nodes")
        assert plot.get("prohibitions")
