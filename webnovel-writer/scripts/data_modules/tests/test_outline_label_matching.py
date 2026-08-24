"""Tests for markdown-variant outline label matching (P0-2)."""
import pytest

from chapter_outline_loader import (
    _clean_plot_line,
    parse_chapter_plot_structure,
)


class TestCleanPlotLineStripsMarkdown:
    def test_strips_bold_markers(self):
        assert _clean_plot_line("**必须覆盖节点**") == "必须覆盖节点"

    def test_strips_list_bullet_with_bold(self):
        assert _clean_plot_line("- **必须覆盖节点**：主角觉醒金手指") != ""

    def test_strips_heading_hashes(self):
        assert "#" not in _clean_plot_line("### 必须覆盖节点")

    def test_plain_text_unchanged(self):
        assert _clean_plot_line("普通描述行") == "普通描述行"


class TestParsePlotStructureMarkdownVariants:
    """must_cover_nodes should be extracted even when labels use bold/heading format."""

    SAMPLE = """
### 第3章 试炼

**目标**：通过试炼获得认可

### 必须覆盖节点
- 主角进入试炼场
- 主角击败对手
- 主角获得奖励

**本章禁区**：
- 不得暴露真实身份
"""

    def test_bold_label_extracts_nodes(self):
        text = "**目标**：测试\n**必须覆盖节点**：主角进入试炼、主角击败对手"
        result = parse_chapter_plot_structure(text)
        nodes = result.get("must_cover_nodes") or result.get("mandatory_nodes") or []
        assert len(nodes) > 0, f"Expected nodes from bold label, got: {result}"

    def test_heading_section_extracts_nodes(self):
        result = parse_chapter_plot_structure(self.SAMPLE)
        nodes = (
            result.get("must_cover_nodes")
            or result.get("mandatory_nodes")
            or []
        )
        assert len(nodes) > 0, f"Expected nodes from heading section, got: {result}"

    def test_forbidden_zones_from_bold(self):
        text = "**本章禁区**：不得暴露身份"
        result = parse_chapter_plot_structure(text)
        zones = result.get("forbidden_zones") or result.get("prohibitions") or []
        assert len(zones) > 0, f"Expected zones from bold label, got: {result}"
