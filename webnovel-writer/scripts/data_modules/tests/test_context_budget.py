#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""context_budget 测试：load_context 的 section 配额与总预算执行（S1/C1）。

配额默认值与 docs/reports/2026-08-30-S1-预算配额分析.md 的推导一一对应。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from data_modules.context_budget import (  # noqa: E402
    DROP_ORDER,
    SECTION_QUOTAS,
    SUB_QUOTAS,
    apply_quota,
    enforce_budget,
    estimate_tokens,
    shrink_latest_commit,
)


def test_quota_defaults_match_analysis():
    """配额默认值 = 分析报告的推导值（改动须同步报告）。"""
    assert SECTION_QUOTAS["story_contracts"] == 8300
    assert SECTION_QUOTAS["runtime_status"] == 700
    assert SECTION_QUOTAS["memory_pack"] == 8500
    assert SECTION_QUOTAS["outline"] == 1500
    assert SECTION_QUOTAS["protagonist"] == 1500
    assert SECTION_QUOTAS["genre_profile_excerpt"] == 1500
    assert SUB_QUOTAS["story_contracts"] == {
        "master": 2800, "volume": 1000, "chapter": 3500, "review": 1000,
    }
    assert SUB_QUOTAS["memory_pack"] == {
        "semantic_memory": 3500, "working_memory": 2500,
        "recent_changes": 1500, "episodic_memory": 1000,
    }
    # 硬约束类永不被整体丢弃
    assert "story_contracts" not in DROP_ORDER
    assert "runtime_status" not in DROP_ORDER


def test_estimate_tokens_is_char_based():
    assert estimate_tokens({"a": "钱平"}) == len(json.dumps({"a": "钱平"}, ensure_ascii=False))
    assert estimate_tokens({}) == 2  # "{}"


def test_apply_quota_truncates_string():
    out = apply_quota("长" * 3000, 100)
    assert len(out) <= 100
    assert out.endswith("（预算截断）")


def test_apply_quota_dict_drops_unlisted_keys_first():
    master = {
        "meta": {"x": 1},
        "route": {"primary_genre": "都市"},
        "master_constraints": ["不崩人设"],
        "base_context": "背" * 2000,
        "source_trace": "溯" * 2200,
        "override_policy": {"a": 1},
    }
    out = apply_quota(master, 2800, priority=["route", "master_constraints", "base_context", "meta"])
    assert "source_trace" not in out
    assert "override_policy" not in out
    assert "route" in out and "master_constraints" in out
    assert estimate_tokens(out) <= 2800


def test_apply_quota_list_keeps_prefix_items():
    items = [{"id": i, "v": "值" * 40} for i in range(10)]
    out = apply_quota(items, 300)
    assert 0 < len(out) < 10
    assert estimate_tokens(out) <= 300


def test_shrink_latest_commit_keeps_meta_and_summary():
    commit = {
        "meta": {"chapter": 35, "status": "accepted"},
        "contract_refs": {"master": "MASTER_SETTING.json"},
        "provenance": {"write_fact_role": "chapter_commit"},
        "outline_snapshot": {"covered": "细" * 2000},
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {"planned": "节" * 2000},
        "disambiguation_result": {"pending": []},
        "extraction_result": {"summary_text": "上一章摘要一句话", "accepted_events": ["e" * 5000]},
        "projection_status": {"state": "done", "index": "done"},
    }
    out = shrink_latest_commit(commit)
    assert out["meta"]["status"] == "accepted"
    assert out["extraction_summary"] == "上一章摘要一句话"
    assert "extraction_result" not in out
    assert "outline_snapshot" not in out
    assert estimate_tokens(out) <= 700


def test_enforce_budget_shrinks_fantasy01_like_sections():
    sections = {
        "story_contracts": {
            "master": {"meta": {}, "route": {"g": 1}, "base_context": "背" * 2400, "source_trace": "溯" * 2200},
            "volume": {"meta": {}},
            "chapter": {
                "meta": {}, "chapter_directive": {"goal": "目标"},
                "dynamic_context": "动" * 5200, "source_trace": "溯" * 2200,
            },
            "review": {"meta": {}},
        },
        "runtime_status": {
            "chapter": 35, "fallback_sources": [], "primary_write_source": "chapter_commit",
            "latest_commit": {
                "meta": {"chapter": 35, "status": "accepted"},
                "outline_snapshot": {"covered": "细" * 4800},
                "fulfillment_result": {"planned": "节" * 4800},
                "extraction_result": {"summary_text": "上一章摘要", "accepted_events": ["提" * 11000]},
            },
            "latest_accepted_chapter": 35,
        },
        "memory_pack": {
            "semantic_memory": [{"id": f"m{i}", "v": "事" * 100} for i in range(30)],
            "working_memory": [{"source": "state_export", "content": {"p": "状" * 2000}}],
            "episodic_memory": [{"id": i, "v": "情" * 60} for i in range(10)],
            "recent_changes": [{"row": i, "v": "变" * 60} for i in range(10)],
        },
        "protagonist": {"name": "苏小白", "current": "状" * 1400},
        "recent_summaries": {"ch0034": "摘" * 300},
        "active_rules": [{"rule": "规" * 200}],
        "urgent_loops": [{"loop": "伏" * 100}],
    }
    used_before = sum(estimate_tokens(v) for v in sections.values())
    assert used_before > 40000  # 与 fantasy01 实测（59,977 字符）同量级

    out, stats = enforce_budget(sections, total_budget=20000)

    for name, quota in SECTION_QUOTAS.items():
        if name in out:
            assert estimate_tokens(out[name]) <= quota, f"{name} 超配额"
    assert "source_trace" not in out["story_contracts"]["master"]
    assert "dynamic_context" in out["story_contracts"]["chapter"]  # 低优先级但允许截断保留
    assert "extraction_result" not in out["runtime_status"]["latest_commit"]
    assert out["runtime_status"]["latest_commit"]["meta"]["status"] == "accepted"
    assert 0 < stats["used"] <= 20000
    assert stats["used"] == sum(estimate_tokens(v) for v in out.values())
    assert stats["used_before"] == used_before


def test_enforce_budget_total_drop_order():
    sections = {
        "story_contracts": {"master": {"meta": {}}, "chapter": {"meta": {}}, "volume": {}, "review": {}},
        "runtime_status": {"chapter": 1, "primary_write_source": "chapter_commit"},
        "memory_pack": {
            "semantic_memory": [{"v": "事" * 100}], "working_memory": [],
            "episodic_memory": [{"v": "情" * 100}], "recent_changes": [],
        },
        "author_style_patterns": [{"p": "风" * 200}],
        "genre_profile_excerpt": "题" * 200,
        "progress": {"a": 1},
        "active_rules": [{"r": 1}],
        "protagonist": {"name": "x"},
        "recent_summaries": {"ch0001": "s"},
        "urgent_loops": [{"l": 1}],
    }

    out, stats = enforce_budget(sections, total_budget=500)

    # 丢弃顺序：低价值 section 先消失，硬约束类保留到最后
    assert "author_style_patterns" not in out
    assert "genre_profile_excerpt" not in out
    assert "story_contracts" in out and "runtime_status" in out
    assert stats["dropped"][:2] == ["memory_pack.episodic_memory", "author_style_patterns"]
    assert stats["used"] == sum(estimate_tokens(v) for v in out.values())


def test_enforce_budget_reports_truncated_sections():
    """S23：配额层实际截断的 section 名单进 stats（占用信号，供按书校准判断）。"""
    sections = {
        "story_contracts": {"master": "m" * 100, "chapter": "c" * 100},
        "protagonist": "p" * 3000,  # 配额 1500 → 触发截断
        "outline": "o" * 50,  # 未触配额
        "recent_summaries": ["s" * 10],
    }

    out, stats = enforce_budget(sections, total_budget=20000)

    assert "protagonist" in stats["truncated_sections"]
    assert "outline" not in stats["truncated_sections"]
    assert "story_contracts" not in stats["truncated_sections"]
