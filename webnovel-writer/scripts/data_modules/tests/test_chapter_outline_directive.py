#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json

from chapter_outline_loader import load_chapter_execution_directive


def test_load_chapter_execution_directive_from_volume_outline(tmp_path):
    outline_dir = tmp_path / "大纲"
    outline_dir.mkdir()
    (tmp_path / ".webnovel").mkdir()
    (tmp_path / ".webnovel" / "state.json").write_text(
        json.dumps({"progress": {"volumes_planned": [{"volume": 1, "chapters_range": "1-50"}]}}),
        encoding="utf-8",
    )
    (outline_dir / "第1卷-详细大纲.md").write_text(
        "\n".join(
            [
                "### 第一章：债从天降",
                "- 目标：搞清楚借据条款的荒谬",
                "- 阻力：杂役不能随意离开宗门",
                "- 代价：暴露自己懂账",
                "- 时间锚点：D-Day 清晨",
                "- 章内跨度：一炷香",
                "- 倒计时状态：三日内还债",
                "- Strand：债务调查",
                "- 反派层级：小反派",
                "- 关键实体：陆鸣、借据、利息",
                "- CBN：醒来发现债务",
                "- CPNs：检查借据；发现复利陷阱",
                "- CEN：决定去井边打听",
                "- 必须覆盖节点：借据金额；复利算法",
                "- 本章禁区：不得离开宗门；不得提前摊牌",
                "- 章末未闭合问题：谁改了借据？",
                "- 钩子类型：信息钩",
                "- 钩子强度：中",
                "",
                "### 第二章：井边口风",
                "- 目标：打听债主来历",
            ]
        ),
        encoding="utf-8",
    )

    directive = load_chapter_execution_directive(tmp_path, 1)

    assert directive["goal"] == "搞清楚借据条款的荒谬"
    assert directive["time_anchor"] == "D-Day 清晨"
    assert directive["chapter_span"] == "一炷香"
    assert directive["countdown"] == "三日内还债"
    assert directive["cpns"] == ["检查借据", "发现复利陷阱"]
    assert "不得离开宗门" in directive["forbidden_zones"]
    assert "借据" in directive["key_entities"]
    assert directive["chapter_end_open_question"] == "谁改了借据？"


def test_load_chapter_outline_truncates_by_field_priority(tmp_path):
    """P2-2：截断时优先保留 CBN/CPNs/CEN/必须覆盖节点/本章禁区。"""
    from chapter_outline_loader import load_chapter_outline

    outline_dir = tmp_path / "大纲"
    outline_dir.mkdir()
    (tmp_path / ".webnovel").mkdir()
    (tmp_path / ".webnovel" / "state.json").write_text(
        json.dumps({"progress": {"volumes_planned": [{"volume": 1, "chapters_range": "1-50"}]}}),
        encoding="utf-8",
    )
    long_desc = "这是很长的描述文本。" * 200
    (outline_dir / "第1卷-详细大纲.md").write_text(
        "\n".join([
            "### 第1章：测试",
            long_desc,
            "CBN：关键节点描述",
            "CPNs：关键节点1；关键节点2",
            "CEN：章末事件",
            "必须覆盖节点：节点A；节点B",
            "本章禁区：不可做某事",
            "",
            "### 第2章：下一章",
        ]),
        encoding="utf-8",
    )

    outline = load_chapter_outline(tmp_path, 1, max_chars=500)

    # 关键字段全部保留
    assert "CBN：关键节点描述" in outline
    assert "CPNs：" in outline
    assert "CEN：章末事件" in outline
    assert "必须覆盖节点" in outline
    assert "本章禁区" in outline
    # 截断标记存在
    assert "已按字段优先级截断" in outline
    # 总长度受控
    assert len(outline) <= 600
