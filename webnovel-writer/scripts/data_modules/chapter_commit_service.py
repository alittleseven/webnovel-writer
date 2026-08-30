#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from chapter_outline_loader import volume_num_for_chapter_from_state

from .chapter_commit_schema import (
    DisambiguationResult,
    ExtractionResult,
    FulfillmentResult,
    ReviewResult,
)
from .commit_artifacts import extraction_list
from .config import DataModulesConfig
from .event_log_store import EventLogStore
from .event_projection_router import EventProjectionRouter
from .story_contracts import write_json
from .index_manager import IndexManager
from .override_ledger_service import (
    AmendProposalTrigger,
    ensure_override_ledger_columns,
    persist_amend_proposals,
)

import logging

logger = logging.getLogger(__name__)


class ChapterCommitService:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    @staticmethod
    def _extraction_warnings(
        chapter: int,
        state_deltas: list[dict[str, Any]],
        entity_deltas: list[dict[str, Any]],
        accepted_events: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """轻量规则校验（P0-4 第一步）：对 data-agent 提取结果做纯结构断言。

        只做可离线判断的规则检查，不阻断提交（标 extraction_warning 供
        /webnovel-query 与 doctor 暴露），避免引入重 LLM 成本。
        """
        warnings: list[dict[str, str]] = []

        # 1. 新实体（upsert 且无别名）——消歧依赖 aliases，缺别名易误分裂。
        for delta in entity_deltas:
            if not isinstance(delta, dict):
                continue
            action = str(delta.get("action") or "upsert")
            payload = delta.get("payload") or {}
            if not isinstance(payload, dict):
                payload = {}
            entity_id = str(delta.get("entity_id") or "").strip()
            aliases = payload.get("aliases") or payload.get("alias") or []
            alias_count = len(aliases) if isinstance(aliases, list) else 1
            if action in {"upsert", "create", "new"} and entity_id and not aliases:
                warnings.append(
                    {
                        "code": "new_entity_missing_aliases",
                        "entity_id": entity_id,
                        "detail": "新增/更新实体缺少 aliases，消歧可能失效",
                    }
                )
            elif action in {"upsert", "create", "new"} and entity_id and alias_count < 3:
                # S8/P2-3：别名预注册——新实体建议 3-5 个别名（全名/简称/称号等变体），
                # 单别名在后续章节的指称消歧中容易 NOT_FOUND。
                warnings.append(
                    {
                        "code": "new_entity_few_aliases",
                        "entity_id": entity_id,
                        "detail": f"新增实体仅 {alias_count} 个别名，建议预注册 3-5 个（全名/简称/称号等变体）",
                    }
                )

        # 2. state_delta 缺 old 或 new —— 境界变化必须带旧值才能判断单调性。
        for delta in state_deltas:
            if not isinstance(delta, dict):
                continue
            field_name = str(delta.get("field") or "").strip()
            has_old = "old" in delta and str(delta.get("old") or "").strip()
            has_new = "new" in delta and str(delta.get("new") or "").strip()
            if field_name and (not has_old or not has_new):
                warnings.append(
                    {
                        "code": "state_delta_missing_old_or_new",
                        "entity_id": str(delta.get("entity_id") or "").strip(),
                        "field": field_name,
                        "detail": "state_delta 缺少 old 或 new，无法校验状态单调性",
                    }
                )

        # 3. accepted_event 章号与当前章不符 —— 时间线章号应一致。
        #    P0-4b：data-agent 产出非整数章号（如 "五"/"3.5"/"xian"）时降级为
        #    warning 而非崩溃，避免轻校验反成新阻断点。
        for event in accepted_events:
            if not isinstance(event, dict):
                continue
            event_chapter = event.get("chapter")
            if event_chapter is None:
                continue
            try:
                parsed_event_chapter = int(event_chapter)
            except (TypeError, ValueError):
                warnings.append(
                    {
                        "code": "event_chapter_unparseable",
                        "event_id": str(event.get("event_id") or "").strip(),
                        "detail": f"事件章号 {event_chapter!r} 无法解析为整数，跳过章号比对",
                    }
                )
                continue
            if parsed_event_chapter != int(chapter):
                warnings.append(
                    {
                        "code": "event_chapter_mismatch",
                        "event_id": str(event.get("event_id") or "").strip(),
                        "detail": f"事件章号 {event_chapter} 与当前章 {chapter} 不符",
                    }
                )

        return warnings

    def build_commit(
        self,
        chapter: int,
        review_result: Dict[str, Any],
        fulfillment_result: Dict[str, Any],
        disambiguation_result: Dict[str, Any],
        extraction_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        review = ReviewResult.model_validate(review_result)
        fulfillment = FulfillmentResult.model_validate(fulfillment_result)
        disambiguation = DisambiguationResult.model_validate(disambiguation_result)
        extraction = ExtractionResult.model_validate(extraction_result)
        rejected = bool(review.blocking_count) or bool(
            fulfillment.missed_nodes
        ) or bool(disambiguation.pending)
        status = "rejected" if rejected else "accepted"
        volume = volume_num_for_chapter_from_state(self.project_root, chapter) or 1
        accepted_events = EventLogStore(self.project_root).normalize_events(
            chapter, extraction.accepted_events
        )
        extraction_payload = extraction.model_dump()
        extraction_payload["accepted_events"] = accepted_events
        extraction_warnings = self._extraction_warnings(
            chapter=chapter,
            state_deltas=extraction.state_deltas,
            entity_deltas=extraction.entity_deltas,
            # 用原始事件做章号检查：normalize 会把非整数章号回退为当前章，
            # 用原始值才能捕获 event_chapter_unparseable / event_chapter_mismatch。
            accepted_events=extraction.accepted_events,
        )
        return {
            "meta": {
                "schema_version": "story-system/v1",
                "chapter": chapter,
                "status": status,
                "extraction_warnings": extraction_warnings,
            },
            "contract_refs": {
                "master": "MASTER_SETTING.json",
                "volume": f"volume_{volume:03d}.json",
                "chapter": f"chapter_{chapter:03d}.json",
                "review": f"chapter_{chapter:03d}.review.json",
            },
            "provenance": {
                "write_fact_role": "chapter_commit",
                "projection_role": "derived_read_models",
                "legacy_state_role": "projection_only",
            },
            "outline_snapshot": {
                "planned_nodes": fulfillment.planned_nodes,
                "covered_nodes": fulfillment.covered_nodes,
                "missed_nodes": fulfillment.missed_nodes,
                "extra_nodes": fulfillment.extra_nodes,
            },
            "review_result": review.model_dump(),
            "fulfillment_result": fulfillment.model_dump(),
            "disambiguation_result": disambiguation.model_dump(),
            "extraction_result": extraction_payload,
            "projection_status": {
                "state": "pending",
                "index": "pending",
                "summary": "pending",
                "memory": "pending",
                "vector": "pending",
            },
        }

    def persist_commit(self, payload: Dict[str, Any]) -> Path:
        target = self.project_root / ".story-system" / "commits"
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"chapter_{int(payload['meta']['chapter']):03d}.commit.json"
        write_json(path, payload)
        self._update_latest_pointer(target, payload)
        return path

    def _update_latest_pointer(self, commits_dir: Path, payload: Dict[str, Any]) -> None:
        """S7：维护 latest.json 指针（max 语义，回头补写不回退），避免读侧逐章回扫。"""
        import json
        import time

        chapter = int(payload["meta"]["chapter"])
        pointer_path = commits_dir / "latest.json"
        previous: Dict[str, Any] = {}
        if pointer_path.exists():
            try:
                previous = json.loads(pointer_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                previous = {}
        latest = max(int(previous.get("latest_chapter") or 0), chapter)
        accepted = int(previous.get("latest_accepted_chapter") or 0)
        if str((payload.get("meta") or {}).get("status")) == "accepted":
            accepted = max(accepted, chapter)
        pointer = {
            "latest_chapter": latest,
            "latest_accepted_chapter": accepted,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        write_json(pointer_path, pointer)

    def _projection_writers(self) -> dict[str, Any]:
        from .index_projection_writer import IndexProjectionWriter
        from .memory_projection_writer import MemoryProjectionWriter
        from .state_projection_writer import StateProjectionWriter
        from .summary_projection_writer import SummaryProjectionWriter
        from .vector_projection_writer import VectorProjectionWriter

        return {
            "state": StateProjectionWriter(self.project_root),
            "index": IndexProjectionWriter(self.project_root),
            "summary": SummaryProjectionWriter(self.project_root),
            "memory": MemoryProjectionWriter(self.project_root),
            "vector": VectorProjectionWriter(self.project_root),
        }

    def _writer_status(self, result: dict[str, Any]) -> str:
        if result.get("applied"):
            # P1-9b：applied 但 partial（部分 chunk embedding 失败，仅 BM25 可用）
            # 时透出独立状态，而非吞成 "done"，让缺口在状态层可见、可进 retry。
            if result.get("partial"):
                return "partial"
            return "done"
        reason = str(result.get("reason") or "").strip()
        if reason in {"not_required", "commit_rejected"}:
            return "skipped"
        if reason.startswith("error:"):
            return f"failed:{reason[6:] or 'writer_error'}"
        return "skipped"

    def apply_projection_writers(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        status = str((payload.get("meta") or {}).get("status") or "")
        if status not in {"accepted", "rejected"}:
            return payload

        payload.setdefault("projection_status", {})
        if not isinstance(payload["projection_status"], dict):
            payload["projection_status"] = {}

        writers = self._projection_writers()
        required_writers = set(EventProjectionRouter().required_writers(payload))
        writer_results: dict[str, dict[str, Any]] = {}
        for name, writer in writers.items():
            if name not in required_writers:
                payload["projection_status"][name] = "skipped"
                writer_results[name] = {"status": "skipped", "reason": "not_required"}
                continue
            try:
                result = writer.apply(payload)
                payload["projection_status"][name] = self._writer_status(result)
                writer_results[name] = {
                    "status": payload["projection_status"][name],
                    "result": result,
                }
            except Exception as exc:
                payload["projection_status"][name] = f"failed:{exc}"
                writer_results[name] = {"status": "failed", "error": str(exc)}
        commit_path = self.persist_commit(payload)
        try:
            from .projection_log import append_projection_run

            append_projection_run(
                self.project_root,
                payload,
                writer_results,
                commit_path=commit_path,
            )
        except Exception as exc:
            # 审计记录失败不应静默吞掉，至少留痕，避免审计链在无感知下丢失。
            logger.error("append_projection_run failed: %s", exc)
        return payload

    def write_events_and_proposals(self, payload: Dict[str, Any]) -> None:
        """写入事件审计链 + 生成修订提案（accepted commit 的写后副作用）。

        从 apply_projections 抽出，供 apply_projections 与 retry_projection 复用，
        修复"commit persist 后崩溃、retry 补跑不写 events → 审计链断链"的窗口。
        """
        status = str((payload.get("meta") or {}).get("status") or "")
        if status != "accepted":
            return

        chapter = int((payload.get("meta") or {}).get("chapter") or 0)
        event_store = EventLogStore(self.project_root)
        accepted_events = extraction_list(payload, "accepted_events")
        extraction = payload.setdefault("extraction_result", {})
        if not isinstance(extraction, dict):
            extraction = {}
            payload["extraction_result"] = extraction
        extraction["accepted_events"] = event_store.normalize_events(
            chapter, accepted_events
        )
        event_store.write_events(chapter, extraction["accepted_events"])

        proposals = AmendProposalTrigger().check(chapter, extraction["accepted_events"])
        if proposals:
            manager = IndexManager(DataModulesConfig.from_project_root(self.project_root))
            with manager._get_conn() as conn:
                ensure_override_ledger_columns(conn)
                persist_amend_proposals(conn, chapter, proposals)
                conn.commit()

    def apply_projections(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        status = str((payload.get("meta") or {}).get("status") or "")
        if status not in {"accepted", "rejected"}:
            return payload

        self.write_events_and_proposals(payload)

        return self.apply_projection_writers(payload)


def summarize_commit_payload(payload: Dict[str, Any]) -> str:
    """一行提交结论。完整 payload 已由 persist_commit 落盘真源，stdout 不再重打全文。"""
    meta = payload.get("meta") or {}
    status = str(meta.get("status") or "")
    projections = payload.get("projection_status") or {}
    warnings = meta.get("extraction_warnings") or []
    chapter = meta.get("chapter")
    parts = [
        "OK" if status == "accepted" else "REJECTED",
        f"chapter-commit chapter={chapter}",
        f"status={status}",
    ]
    if projections:
        parts.append("projections=" + ",".join(f"{key}:{value}" for key, value in projections.items()))
    if warnings:
        parts.append(f"warnings={len(warnings)}")
    if isinstance(chapter, int):
        parts.append(f"detail=.story-system/commits/chapter_{chapter:03d}.commit.json")
    return " ".join(parts)
