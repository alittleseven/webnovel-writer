#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, Dict, List

from .commit_artifacts import extraction_list, extraction_text

logger = logging.getLogger(__name__)


class VectorProjectionWriter:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def apply(self, commit_payload: dict) -> dict:
        if commit_payload["meta"]["status"] != "accepted":
            return {"applied": False, "writer": "vector", "reason": "commit_rejected"}

        chunks = self._collect_chunks(commit_payload)
        if not chunks:
            return {"applied": False, "writer": "vector", "reason": "no_chunks"}

        try:
            stored = self._store_chunks(chunks)
            if stored <= 0:
                # embedding 全部失败时，store_chunks 的 fallback 分支会把正文行
                # （embedding 置 NULL）写入 vectors 表并更新 bm25_index，
                # 此时关键词检索仍可用。这里区分「降级成功」与「完全失败」：
                # 只要 vectors 表已写入本章 chunk 行，就视为降级成功（skipped），
                # 避免把 BM25 可用的场景误判为 blocking 失败（P0-2 补充修复）。
                if self._chunks_present_in_vectors(chunks):
                    return {
                        "applied": False,
                        "writer": "vector",
                        "stored": stored,
                        "reason": "embedding_degraded_bm25_fallback",
                    }
                return {
                    "applied": False,
                    "writer": "vector",
                    "stored": stored,
                    "reason": "error:store_failed",
                }
            return {"applied": True, "writer": "vector", "stored": stored}
        except Exception as exc:
            logger.warning("vector_projection_failed: %s", exc)
            return {"applied": False, "writer": "vector", "reason": f"error:{exc}"}

    def _chunks_present_in_vectors(self, chunks: List[Dict[str, Any]]) -> bool:
        """检查 chunk 是否已写入 vectors 表（embedding 置 NULL 也算已写入）。"""
        import sqlite3

        chapter = int(chunks[0].get("chapter") or 0) if chunks else 0
        if chapter <= 0:
            return False
        try:
            from .config import DataModulesConfig

            config = DataModulesConfig.from_project_root(self.project_root)
            with sqlite3.connect(str(config.vector_db)) as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM vectors WHERE chapter = ?",
                    (chapter,),
                ).fetchone()
            return bool(row and row[0] and int(row[0]) > 0)
        except Exception:
            return False

    def _collect_chunks(self, commit_payload: dict) -> List[Dict[str, Any]]:
        chunks: List[Dict[str, Any]] = []
        chapter = int(commit_payload.get("meta", {}).get("chapter") or 0)

        chunk_counts: Dict[str, int] = {}

        summary_text = extraction_text(commit_payload, "summary_text")
        summary_chunk_id = f"ch{chapter:04d}_summary" if chapter > 0 else ""
        if chapter > 0 and summary_text:
            chunks.append({
                "chunk_id": summary_chunk_id,
                "chapter": chapter,
                "scene_index": 0,
                "content": summary_text,
                "chunk_type": "summary",
                "parent_chunk_id": None,
                "source_file": f"commit:chapter_{chapter:03d}",
            })

        for event in extraction_list(commit_payload, "accepted_events"):
            if not isinstance(event, dict):
                continue
            text = self._event_to_text(event)
            if text:
                evt_chapter = int(event.get("chapter") or chapter)
                event_key = event.get("event_id") or f"{event.get('event_type')}:{event.get('subject')}:{text}"
                chunk_id = self._unique_chunk_id(chunk_counts, "event", evt_chapter, event_key)
                chunks.append({
                    "chunk_id": chunk_id,
                    "chapter": evt_chapter,
                    "scene_index": 0,
                    "content": text,
                    "chunk_type": "event",
                    "parent_chunk_id": f"ch{evt_chapter:04d}_summary",
                    "source_file": f"commit:chapter_{evt_chapter:03d}",
                })

        for delta in extraction_list(commit_payload, "entity_deltas"):
            if not isinstance(delta, dict):
                continue
            text = self._delta_to_text(delta)
            if text:
                d_chapter = int(delta.get("chapter") or chapter)
                delta_key = delta.get("delta_id") or delta.get("entity_id") or text
                chunk_id = self._unique_chunk_id(chunk_counts, "entity_delta", d_chapter, delta_key)
                chunks.append({
                    "chunk_id": chunk_id,
                    "chapter": d_chapter,
                    "scene_index": 0,
                    "content": text,
                    "chunk_type": "entity_delta",
                    "parent_chunk_id": f"ch{d_chapter:04d}_summary",
                    "source_file": f"commit:chapter_{d_chapter:03d}",
                })

        for idx, scene in enumerate(extraction_list(commit_payload, "scenes"), start=1):
            if not isinstance(scene, dict):
                continue
            scene_index = int(scene.get("scene_index") or scene.get("index") or idx)
            text = str(scene.get("summary") or scene.get("content") or "").strip()
            location = str(scene.get("location") or "").strip()
            if location and text:
                text = f"{location}：{text}"
            if not text:
                continue
            chunk_id = self._chunk_id("scene", chapter, scene_index)
            chunks.append({
                "chunk_id": chunk_id,
                "chapter": chapter,
                "scene_index": scene_index,
                "content": text,
                "chunk_type": "scene",
                "parent_chunk_id": summary_chunk_id or None,
                "source_file": f"commit:chapter_{chapter:03d}",
            })

        return chunks

    def _unique_chunk_id(
        self,
        counts: Dict[str, int],
        kind: str,
        chapter: int,
        key: Any,
    ) -> str:
        base_id = self._chunk_id(kind, chapter, key)
        occurrence = counts.get(base_id, 0) + 1
        counts[base_id] = occurrence
        return base_id if occurrence == 1 else f"{base_id}_{occurrence}"

    def _chunk_id(self, kind: str, chapter: int, key: Any) -> str:
        raw = f"{kind}:{chapter}:{key}"
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        return f"ch{chapter:04d}_{kind}_{digest}"

    def _event_to_text(self, event: dict) -> str:
        chapter = int(event.get("chapter") or 0)
        subject = str(event.get("subject") or "").strip()
        event_type = str(event.get("event_type") or "").strip()
        payload = event.get("payload") or {}

        if event_type == "power_breakthrough":
            new_val = str(
                payload.get("new")
                or payload.get("to")
                or payload.get("new_value")
                or payload.get("new_state")
                or ""
            ).strip()
            return f"第{chapter}章：{subject}突破至{new_val}" if new_val else ""
        elif event_type == "character_state_changed":
            field = str(
                payload.get("field") or payload.get("field_path") or ""
            ).strip()
            new_val = str(
                payload.get("new")
                or payload.get("to")
                or payload.get("new_value")
                or payload.get("new_state")
                or ""
            ).strip()
            description = str(payload.get("description") or "").strip()
            if field and new_val:
                return f"第{chapter}章：{subject}的{field}变为{new_val}"
            if new_val:
                return f"第{chapter}章：{subject}变化为{new_val}"
            if description:
                return f"第{chapter}章：{subject}：{description}"
            return ""
        elif event_type == "relationship_changed":
            to_entity = str(payload.get("to_entity") or payload.get("to") or "").strip()
            rel_type = str(payload.get("relationship_type") or payload.get("type") or "").strip()
            return f"第{chapter}章：{subject}与{to_entity}关系变为{rel_type}" if to_entity else ""
        elif event_type in ("world_rule_revealed", "world_rule_broken"):
            desc = str(
                payload.get("description")
                or payload.get("rule")
                or payload.get("rule_content")
                or ""
            ).strip()
            action = "揭示" if "revealed" in event_type else "打破"
            return f"第{chapter}章：{action}世界规则——{desc}" if desc else ""
        elif event_type == "open_loop_created":
            description = str(
                payload.get("description")
                or payload.get("unanswered_question")
                or payload.get("content")
                or ""
            ).strip()
            return f"第{chapter}章：{subject}埋下悬念——{description}" if description else ""
        elif event_type == "artifact_obtained":
            name = str(payload.get("name") or subject or "").strip()
            owner = str(payload.get("owner") or payload.get("holder") or "").strip()
            return f"第{chapter}章：{owner}获得{name}" if owner else f"第{chapter}章：获得{name}"
        return ""

    def _delta_to_text(self, delta: dict) -> str:
        chapter = int(delta.get("chapter") or 0)
        from_e = str(delta.get("from_entity") or "").strip()
        to_e = str(delta.get("to_entity") or "").strip()
        rel = str(delta.get("relationship_type") or "").strip()

        if from_e and to_e and rel:
            return f"第{chapter}章：{from_e}与{to_e}关系变为{rel}"

        entity_id = str(delta.get("entity_id") or "").strip()
        canonical = str(delta.get("canonical_name") or entity_id).strip()
        if entity_id:
            return f"第{chapter}章：实体变更——{canonical}"
        return ""

    def _run_store_coro(self, coro: Coroutine[Any, Any, int]) -> int:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return int(asyncio.run(coro) or 0)

        result: Dict[str, Any] = {}

        def runner() -> None:
            try:
                result["value"] = asyncio.run(coro)
            except Exception as exc:
                result["error"] = exc

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()
        if "error" in result:
            raise result["error"]
        return int(result.get("value") or 0)

    def _store_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        from .config import DataModulesConfig
        from .rag_adapter import RAGAdapter

        config = DataModulesConfig.from_project_root(self.project_root)
        adapter = RAGAdapter(config)
        try:
            return self._run_store_coro(adapter.store_chunks(chunks))
        except Exception as exc:
            logger.warning("vector_store_failed: %s", exc)
            return 0
