#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from ..artifact_validator import validate_chapter_commit
from ..artifact_validator import OK_PROJECTION_STATUSES, REQUIRED_PROJECTION_WRITERS
from ..config import DataModulesConfig
from ..project_phase import resolve_project_phase
from ..projection_log import latest_projection_run, projection_status_from_run
from . import gate_report, issue


def _commit_path(project_root: Path, chapter: int) -> Path:
    return project_root / ".story-system" / "commits" / f"chapter_{chapter:03d}.commit.json"


def _projection_status_from_runtime(
    project_root: Path,
    chapter: int,
    payload: dict,
) -> tuple[dict[str, str], str, dict]:
    try:
        latest_run = latest_projection_run(project_root, chapter=chapter)
        logged_status = projection_status_from_run(latest_run)
    except Exception:
        latest_run = None
        logged_status = {}
    if logged_status:
        return logged_status, "projection_log", latest_run or {}

    raw_status = payload.get("projection_status") if isinstance(payload, dict) else {}
    if isinstance(raw_status, dict):
        return {str(key): str(value) for key, value in raw_status.items()}, "commit", {}
    return {}, "commit", {}


def run_postcommit_gate(project_root: Path, chapter: int) -> dict:
    snapshot = resolve_project_phase(project_root, chapter=chapter)
    errors: list[dict] = []
    warnings: list[dict] = []
    commit_path = _commit_path(project_root, chapter)
    commit_report = validate_chapter_commit(commit_path)

    for item in commit_report.get("errors") or []:
        errors.append(
            issue(
                f"commit.{item.get('type')}",
                message=str(item.get("message") or ""),
                path=str(item.get("path") or commit_path),
                impact=str(item.get("impact") or ""),
                repair=str(item.get("repair") or ""),
                details=item,
            )
        )

    payload = commit_report.get("payload") if isinstance(commit_report.get("payload"), dict) else {}
    meta = payload.get("meta") if isinstance(payload, dict) else {}
    status = str((meta or {}).get("status") or "")
    if commit_path.is_file() and status != "accepted":
        errors.append(
            issue(
                "commit_not_accepted",
                message=f"chapter commit status is {status or 'missing'}",
                path=str(commit_path),
                impact="写章充分性闸门要求 accepted commit 才能进入备份和下一章。",
                repair="修复 review/fulfillment/disambiguation 阻断项后重新提交。",
            )
        )

    projection_status, projection_source, projection_run = _projection_status_from_runtime(
        project_root,
        chapter,
        payload,
    )
    if isinstance(projection_status, dict):
        for writer in REQUIRED_PROJECTION_WRITERS:
            status_text = str(projection_status.get(writer) or "").strip()
            if not status_text:
                errors.append(
                    issue(
                        "projection_status_missing",
                        message=f"projection {writer} status missing",
                        path=str(commit_path),
                        impact="postcommit 必须确认 state/index/summary/memory/vector 五项投影状态。",
                        repair="重新执行 chapter-commit 或补跑 projection retry/replay。",
                        details={"source": projection_source},
                    )
                )
            elif status_text.startswith("failed"):
                errors.append(
                    issue(
                        "projection_failure",
                        message=f"projection {writer} failed: {status_text}",
                        path=str(commit_path),
                        impact="最新 projection_log 显示 read-model 投影失败。",
                        repair="查看 projection_log.jsonl 的 writers 字段，修复后补跑 projection retry/replay。",
                        details={"source": projection_source, "run": projection_run},
                    )
                )
            elif status_text == "pending":
                errors.append(
                    issue(
                        "projection_pending",
                        message=f"projection {writer} is still pending",
                        path=str(commit_path),
                        impact="read-model 还没有确认写入完成。",
                        repair="重新运行 chapter-commit 或后续 projection retry/replay。",
                    )
                )
            elif status_text == "partial":
                # P1-9b：partial 是「可接受的降级状态」，不阻断，但要在
                # postcommit 提示语义检索缺口，让用户可主动 retry 补齐。
                warnings.append(
                    issue(
                        "projection_partial",
                        message=f"projection {writer} partial: 部分 chunk 语义向量缺失（BM25 仍可用）",
                        path=str(commit_path),
                        severity="warning",
                        impact="本章部分内容无语义向量，关键词检索可用但语义检索有缺口。",
                        repair="补跑 projections retry/replay 以补齐 embedding。",
                    )
                )
            elif status_text not in OK_PROJECTION_STATUSES:
                errors.append(
                    issue(
                        "projection_status_invalid",
                        message=f"projection {writer} status is {status_text}",
                        path=str(commit_path),
                        impact="postcommit 只接受 projection 状态 done 或 skipped。",
                        repair="等待投影完成或补跑 projection retry/replay。",
                    )
                )

    cfg = DataModulesConfig.from_project_root(project_root)
    if isinstance(projection_status, dict) and projection_status.get("summary") == "done":
        summary_path = cfg.webnovel_dir / "summaries" / f"ch{chapter:04d}.md"
        if not summary_path.is_file():
            errors.append(
                issue(
                    "summary_projection_missing",
                    message="summary projection marked done but file is missing",
                    path=str(summary_path),
                    impact="后续上下文无法读取本章摘要。",
                    repair="补跑 summary projection 或重新执行 chapter-commit。",
                )
            )
    if isinstance(projection_status, dict) and projection_status.get("index") == "done" and not cfg.index_db.is_file():
        errors.append(
            issue(
                "index_projection_missing",
                message="index projection marked done but index.db is missing",
                path=str(cfg.index_db),
                impact="查询、dashboard 和实体关系读模型不可用。",
                repair="补跑 index projection 或重新执行 chapter-commit。",
            )
        )
    if isinstance(projection_status, dict) and projection_status.get("memory") == "done" and not cfg.scratchpad_file.is_file():
        warnings.append(
            issue(
                "memory_projection_missing",
                message="memory projection marked done but scratchpad is missing",
                severity="warning",
                path=str(cfg.scratchpad_file),
                impact="长期记忆可能未写入。",
                repair="检查 memory projection 输出；必要时补跑。",
            )
        )

    return gate_report(
        stage="postcommit",
        project_root=project_root,
        chapter=chapter,
        phase=snapshot.phase,
        errors=errors,
        warnings=warnings,
        details={
            "phase": snapshot.to_dict(),
            "commit_path": str(commit_path),
            "commit_report": commit_report,
            "projection_source": projection_source,
            "projection_run": projection_run,
        },
    )
