#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..prewrite_validator import PrewriteValidator
from ..timeline_check import check_timeline
from . import gate_report, issue
from ..project_phase import (
    PHASE_CHAPTER_CONTRACT_READY,
    PHASE_DRAFT_IN_PROGRESS,
    PHASE_READY_TO_COMMIT,
    resolve_project_phase,
)
from ..story_runtime_sources import load_runtime_sources


ALLOWED_PREWRITE_PHASES = {
    PHASE_CHAPTER_CONTRACT_READY,
    PHASE_DRAFT_IN_PROGRESS,
    PHASE_READY_TO_COMMIT,
}


def _plot_structure(chapter_contract: dict[str, Any], review_contract: dict[str, Any]) -> dict[str, Any]:
    """S6：字段名统一后只读准绳名 must_cover_nodes/forbidden_zones（blocking_rules 为审查规则，保留兜底）。"""
    directive = chapter_contract.get("chapter_directive") if isinstance(chapter_contract, dict) else {}
    if not isinstance(directive, dict):
        directive = {}
    return {
        "must_cover_nodes": list(
            directive.get("must_cover_nodes")
            or review_contract.get("must_cover_nodes")
            or []
        ),
        "forbidden_zones": list(
            directive.get("forbidden_zones")
            or review_contract.get("blocking_rules")
            or []
        ),
    }


def run_prewrite_gate(project_root: Path, chapter: int) -> dict[str, Any]:
    snapshot = resolve_project_phase(project_root, chapter=chapter)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if snapshot.phase not in ALLOWED_PREWRITE_PHASES:
        errors.append(
            issue(
                "phase_not_ready_for_prewrite",
                message=f"phase {snapshot.phase} is not ready for prewrite",
                impact="写前合同或项目骨架不完整，继续写作容易使用旧上下文或缺失约束。",
                repair="先运行 project-status/doctor，根据 next_action 补齐 init、plan 或 Story System 合同。",
                details=snapshot.to_dict(),
            )
        )

    # S18/E4：双格式唯一写入路径——v7 侧已落定该章时阻断 v6 写入
    from ..config import DataModulesConfig
    from ..dual_format_guard import check_unique_write_path

    _cfg = DataModulesConfig.from_project_root(project_root)
    _repo_root = str(getattr(_cfg, "story_repo_root", "") or "")
    guard_issue = check_unique_write_path(
        project_root, chapter, target_format="v6", story_repo_root=_repo_root or None
    )
    if guard_issue:
        errors.append(guard_issue)

    runtime = load_runtime_sources(project_root, chapter)
    contracts = runtime.contracts
    story_contract = {
        "master_setting": contracts.get("master") or {},
        "volume_brief": contracts.get("volume") or {},
        "chapter_brief": contracts.get("chapter") or {},
        "review_contract": contracts.get("review") or {},
    }
    review_contract = contracts.get("review") or {}
    plot_structure = _plot_structure(contracts.get("chapter") or {}, review_contract)

    validation = PrewriteValidator(project_root).build(
        chapter=chapter,
        review_contract=review_contract,
        plot_structure=plot_structure,
        story_contract=story_contract,
    )
    if validation.get("blocking"):
        errors.append(
            issue(
                "prewrite_validator_blocking",
                message="prewrite validator reported blocking issue(s)",
                impact="当前章节写作输入不可信。",
                repair="按 blocking_reasons 补齐合同、消歧 pending 或相关占位符。",
                details=validation,
            )
        )
    elif runtime.fallback_sources:
        warnings.append(
            issue(
                "story_runtime_fallback",
                message="story runtime has fallback sources",
                severity="warning",
                impact="写作上下文可能缺少上一章 accepted commit。",
                repair="确认这是第一章或补齐 accepted commit 后再写。",
                details=list(runtime.fallback_sources),
            )
        )

    # P0-4: programmatic timeline check
    volume_num = 1  # default; could be inferred from chapter number in future
    try:
        timeline_report = check_timeline(project_root, volume_num)
        if not timeline_report.get("ok"):
            warnings.append(
                issue(
                    "timeline_check_failed",
                    message="volume timeline check reported issues",
                    severity="warning",
                    impact="时间线可能存在回跳或倒计时错误，影响叙事一致性。",
                    repair="运行 webnovel.py timeline-check --volume {N} 查看详情并修正大纲。",
                    details=timeline_report,
                )
            )
    except Exception:
        pass  # timeline check failure should not crash the gate

    return gate_report(
        stage="prewrite",
        project_root=project_root,
        chapter=chapter,
        phase=snapshot.phase,
        errors=errors,
        warnings=warnings,
        details={
            "phase": snapshot.to_dict(),
            "story_runtime": runtime.to_dict(),
            "prewrite_validation": validation,
            "timeline": timeline_report if "timeline_report" in dir() else None,
        },
    )





