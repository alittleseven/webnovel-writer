#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""context_budget — load_context 的 section 配额与总预算执行（S1/C1）。

配额默认值与推导见 docs/reports/2026-08-30-S1-预算配额分析.md（fantasy01 实测）：
- 字符数 ≈ token 数（CJK 1:1，JSON 键为 ASCII），estimate 以 json.dumps 长度计。
- 截断只允许砍「冗余/元数据/已蒸馏」内容；任务书五段的数据来源为保护对象。
- 硬约束类 section（story_contracts / runtime_status）永不整体丢弃。
"""
from __future__ import annotations

import json
from typing import Any

# section 配额（字符）；依据分析报告 §3 的任务书五段数据来源推导
SECTION_QUOTAS: dict[str, int] = {
    "story_contracts": 8300,
    "runtime_status": 700,
    "memory_pack": 8500,
    "outline": 1500,
    "recent_summaries": 1000,
    "protagonist": 1500,
    "progress": 800,
    "active_rules": 1200,
    "urgent_loops": 1200,
    "genre_profile_excerpt": 1500,
    "author_style_patterns": 2000,
    "style_contract": 2000,
    # M5/T22（R1/W1）：上一章原文尾段与作者已改提醒
    "prev_chapter_tail": 1700,
    "stale_notes": 1200,
    # M5/T25（R4）：追读力信号（近期追读/钩子分布/审查趋势/差异化提醒）
    "reader_signal": 1600,
}

# 嵌套 section 的子配额（memory_pack / story_contracts 内部）
SUB_QUOTAS: dict[str, dict[str, int]] = {
    "story_contracts": {"master": 2800, "volume": 1000, "chapter": 3500, "review": 1000},
    "memory_pack": {
        "semantic_memory": 3500,
        "working_memory": 2500,
        "recent_changes": 1500,
        "episodic_memory": 1000,
    },
}

# 字典键保留优先级：未列出的键先丢弃（source_trace 等元数据不进上下文）
KEY_PRIORITY: dict[str, list[str]] = {
    "master": ["route", "master_constraints", "base_context", "meta"],
    "chapter": ["chapter_directive", "meta", "override_allowed", "reasoning", "dynamic_context"],
    "volume": ["meta", "volume_goal", "beat_table", "timeline"],
    "review": ["meta", "must_cover_nodes", "blocking_rules", "forbidden_zones"],
}

# 超总预算时的丢弃顺序（低价值优先）；story_contracts / runtime_status 为硬约束类，不在表内。
# M5/T22（R5/F-04）：文风层（author_style_patterns / style_contract）与连续性层
# （prev_chapter_tail / stale_notes）提为不可丢——长篇后期恰是最需要文风稳定与
# 上章原文的时期，不再被整体丢弃（超预算走 memory_pack 比例压缩消化）。
PROTECTED_PATHS: tuple[str, ...] = (
    "prev_chapter_tail",
    "stale_notes",
    "author_style_patterns",
    "style_contract",
)
DROP_ORDER: list[str] = [
    "memory_pack.episodic_memory",
    "genre_profile_excerpt",
    "progress",
    "active_rules",
    "protagonist",
    "recent_summaries",
    "memory_pack.recent_changes",
    "memory_pack.working_memory",
    "urgent_loops",
    "memory_pack.semantic_memory",
]

_TRUNCATION_MARK = "…（预算截断）"


def estimate_tokens(value: Any) -> int:
    """token 估算 = json 序列化后的字符数（CJK 1:1；ASCII 键带来少量高估，可接受）。"""
    return len(json.dumps(value, ensure_ascii=False))


def _truncate_str(text: str, quota: int) -> str:
    if len(text) <= quota:
        return text
    keep = max(0, quota - len(_TRUNCATION_MARK))
    return text[:keep] + _TRUNCATION_MARK


def _apply_list_quota(items: list, quota: int) -> list:
    kept: list = []
    used = 2  # "[]"
    for item in items:
        size = estimate_tokens(item) + 1
        if used + size > quota:
            break
        kept.append(item)
        used += size
    return kept


def _apply_dict_quota(value: dict, quota: int, priority: list[str] | None) -> dict:
    out: dict[str, Any] = {}
    used = 2
    keys = [k for k in (priority or list(value.keys())) if k in value]
    # 优先键装不下时允许截断其值；普通键按原序追加
    for key in keys:
        child = value[key]
        remaining = quota - used
        if remaining <= 10:
            break
        sized = estimate_tokens(child)
        if sized <= remaining:
            out[key] = child
            used += sized + 1
        elif isinstance(child, str):
            out[key] = _truncate_str(child, remaining)
            used = quota
            break
        else:
            sub = apply_quota(child, remaining, priority=None)
            out[key] = sub
            used += estimate_tokens(sub) + 1
    return out


def apply_quota(value: Any, quota: int, priority: list[str] | None = None) -> Any:
    if quota <= 0 or value is None:
        return value
    if estimate_tokens(value) <= quota:
        return value
    if isinstance(value, str):
        return _truncate_str(value, quota)
    if isinstance(value, list):
        return _apply_list_quota(value, quota)
    if isinstance(value, dict):
        return _apply_dict_quota(value, quota, priority)
    return value


def shrink_latest_commit(commit: dict[str, Any]) -> dict[str, Any]:
    """上一章提交全文的保留集：meta + 投影状态 + 上一章摘要一句。

    提取细节（events/scenes/fulfillment 等）已被 memory_pack / recent_summaries
    投影蒸馏，全文进入上下文属于重复注入（fantasy01 实测占基础包 39%）。
    """
    out: dict[str, Any] = {}
    if "meta" in commit:
        out["meta"] = commit["meta"]
    if "projection_status" in commit:
        out["projection_status"] = commit["projection_status"]
    summary = ((commit.get("extraction_result") or {}).get("summary_text")) or ""
    if summary:
        out["extraction_summary"] = summary[:300]
    return out


def _get_path(sections: dict[str, Any], path: str) -> Any:
    node: Any = sections
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _remove_path(sections: dict[str, Any], path: str) -> None:
    parts = path.split(".")
    node: Any = sections
    for part in parts[:-1]:
        if not isinstance(node, dict) or part not in node:
            return
        node = node[part]
    if isinstance(node, dict):
        node.pop(parts[-1], None)


def enforce_budget(sections: dict[str, Any], *, total_budget: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """按 section 配额收缩，再按 DROP_ORDER 处理总超预算。

    返回 (新 sections, stats)；stats.used = 收缩后的真实估算，used_before = 原始估算。
    """
    sections = dict(sections)
    used_before = sum(estimate_tokens(v) for v in sections.values())
    dropped: list[str] = []

    # 特例先行：runtime_status.latest_commit 用保留集替换（在配额判定之前）
    runtime = sections.get("runtime_status")
    if isinstance(runtime, dict) and isinstance(runtime.get("latest_commit"), dict):
        sections["runtime_status"] = {
            **runtime,
            "latest_commit": shrink_latest_commit(runtime["latest_commit"]),
        }

    # 第一层：section / 子 section 配额
    quota_before = {name: estimate_tokens(v) for name, v in sections.items()}
    for name, quota in SECTION_QUOTAS.items():
        if name not in sections:
            continue
        priority = None
        if name == "story_contracts":
            contracts = sections[name]
            sections[name] = {
                key: apply_quota(value, SUB_QUOTAS["story_contracts"].get(key, quota), KEY_PRIORITY.get(key))
                for key, value in contracts.items()
            }
            continue
        if name == "memory_pack":
            pack = sections[name]
            sections[name] = {
                key: apply_quota(value, SUB_QUOTAS["memory_pack"].get(key, quota // 2))
                for key, value in pack.items()
                if key != "stats"
            }
            continue
        sections[name] = apply_quota(sections[name], quota, priority)

    def used() -> int:
        return sum(estimate_tokens(v) for v in sections.values())

    # R5/F-04 第二层前半：总预算仍超时，先按比例压缩 memory_pack 子层配额（0.8 步进至 0.4）
    factor = 0.8
    while used() > total_budget and factor >= 0.39 and isinstance(sections.get("memory_pack"), dict):
        scaled = {key: max(200, int(quota * factor)) for key, quota in SUB_QUOTAS["memory_pack"].items()}
        pack = sections["memory_pack"]
        sections["memory_pack"] = {
            key: apply_quota(value, scaled.get(key, 500))
            for key, value in pack.items()
            if key != "stats"
        }
        factor -= 0.2

    # 第二层后半：总预算 — 按 DROP_ORDER 丢低价值路径；硬约束类与 PROTECTED_PATHS 不在表内，永不整体丢弃
    while used() > total_budget and dropped != DROP_ORDER:
        next_path = next((p for p in DROP_ORDER if p not in dropped and _get_path(sections, p) is not None), None)
        if next_path is None:
            break
        _remove_path(sections, next_path)
        dropped.append(next_path)

    stats = {
        "used": used(),
        "used_before": used_before,
        "dropped": dropped,
        "total_budget": total_budget,
        # S23：配额层实际截断的 section 名单（占用信号，供按书校准判断；整体丢弃走 dropped）
        "truncated_sections": [
            n for n, v in sections.items() if n in quota_before and estimate_tokens(v) < quota_before[n]
        ],
    }
    return sections, stats
