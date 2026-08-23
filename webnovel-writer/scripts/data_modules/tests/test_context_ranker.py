#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from data_modules.config import DataModulesConfig
from data_modules.context_ranker import ContextRanker


def test_rank_recent_summaries_prefers_recency_and_hook(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    ranker = ContextRanker(cfg)

    items = [
        {"chapter": 8, "summary": "平稳推进"},
        {"chapter": 9, "summary": "最后留下悬念？"},
        {"chapter": 7, "summary": "老信息"},
    ]

    ranked = ranker.rank_recent_summaries(items, current_chapter=10)
    assert ranked[0]["chapter"] == 9
    assert ranked[-1]["chapter"] == 7


def test_rank_appearances_uses_recency_and_frequency(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    ranker = ContextRanker(cfg)

    items = [
        {"entity_id": "a", "last_chapter": 9, "total": 1},
        {"entity_id": "b", "last_chapter": 8, "total": 8},
        {"entity_id": "c", "last_chapter": 9, "total": 3},
    ]

    ranked = ranker.rank_appearances(items, current_chapter=10)
    ids = [item["entity_id"] for item in ranked]
    assert ids[0] == "c"
    assert ids[-1] in {"a", "b"}


def test_rank_pack_adds_context_contract_meta(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    ranker = ContextRanker(cfg)

    pack = {
        "meta": {"chapter": 12},
        "core": {"recent_summaries": [{"chapter": 11, "summary": "x"}], "recent_meta": []},
        "scene": {"appearing_characters": []},
        "global": {},
        "story_skeleton": [],
        "alerts": {"disambiguation_warnings": [], "disambiguation_pending": []},
    }

    ranked = ranker.rank_pack(pack, chapter=12)
    assert ranked["meta"]["context_contract_version"] == "v2"
    assert ranked["meta"]["ranker"]["enabled"] is True


def test_apply_budget_truncates_long_summary(tmp_path):
    """P1-4：超预算长文本被截断（头部保留 + 中略标记 + 尾部保留）。"""
    cfg = DataModulesConfig.from_project_root(tmp_path)
    ranker = ContextRanker(cfg)

    long_text = "开头关键信息" + "正文" * 500 + "结尾钩子悬念"
    pack = {
        "core": {"recent_summaries": [{"chapter": 11, "summary": long_text}], "recent_meta": []},
        "story_skeleton": [],
    }

    result = ranker.apply_budget(pack)
    summary = result["core"]["recent_summaries"][0]["summary"]
    assert len(summary) < len(long_text)
    assert "中略" in summary
    assert summary.startswith("开头关键信息")


def test_apply_budget_keeps_short_text_untouched(tmp_path):
    """P1-4：短于预算的文本不截断。"""
    cfg = DataModulesConfig.from_project_root(tmp_path)
    ranker = ContextRanker(cfg)

    pack = {
        "core": {"recent_summaries": [{"chapter": 11, "summary": "短摘要"}], "recent_meta": []},
        "story_skeleton": [],
    }

    result = ranker.apply_budget(pack)
    assert result["core"]["recent_summaries"][0]["summary"] == "短摘要"


def test_apply_budget_disabled_returns_pack_unchanged(tmp_path):
    """P1-4：context_compact_text_enabled=False 时零改动。"""
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.context_compact_text_enabled = False
    ranker = ContextRanker(cfg)

    long_text = "x" * 5000
    pack = {
        "core": {"recent_summaries": [{"chapter": 11, "summary": long_text}], "recent_meta": []},
        "story_skeleton": [],
    }

    result = ranker.apply_budget(pack)
    assert result["core"]["recent_summaries"][0]["summary"] == long_text


def test_apply_budget_min_budget_floor(tmp_path):
    """P1-4：条目多时单条预算均分但不低于 context_compact_min_budget。"""
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.context_extra_section_budget = 240
    cfg.context_compact_min_budget = 200
    ranker = ContextRanker(cfg)

    items = [{"chapter": ch, "summary": "y" * 400} for ch in (9, 10, 11)]
    pack = {"core": {"recent_summaries": items, "recent_meta": []}, "story_skeleton": []}

    result = ranker.apply_budget(pack)
    summaries = [row["summary"] for row in result["core"]["recent_summaries"]]
    # 均分 = 240//3 = 80 < min_budget 200 → 每条至少保留 ~200 字符
    assert all(len(s) <= 220 for s in summaries)
    assert all("中略" in s or len(s) <= 200 for s in summaries)


def test_apply_budget_truncates_recent_meta_hook(tmp_path):
    """P1-4：recent_meta 的 hook 字段同样按预算截断。"""
    cfg = DataModulesConfig.from_project_root(tmp_path)
    ranker = ContextRanker(cfg)

    pack = {
        "core": {"recent_summaries": [], "recent_meta": [{"chapter": 11, "hook": "h" * 3000}]},
        "story_skeleton": [],
    }

    result = ranker.apply_budget(pack)
    hook = result["core"]["recent_meta"][0]["hook"]
    assert len(hook) < 3000


def test_rank_pack_applies_budget_at_end(tmp_path):
    """P1-4：rank_pack 末尾自动应用预算截断。"""
    cfg = DataModulesConfig.from_project_root(tmp_path)
    ranker = ContextRanker(cfg)

    pack = {
        "meta": {"chapter": 12},
        "core": {
            "recent_summaries": [{"chapter": 11, "summary": "z" * 3000}],
            "recent_meta": [],
        },
        "scene": {"appearing_characters": []},
        "global": {},
        "story_skeleton": [],
        "alerts": {"disambiguation_warnings": [], "disambiguation_pending": []},
    }

    ranked = ranker.rank_pack(pack, chapter=12)
    assert len(ranked["core"]["recent_summaries"][0]["summary"]) < 3000

