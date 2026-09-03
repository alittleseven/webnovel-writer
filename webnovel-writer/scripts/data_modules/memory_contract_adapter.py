#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MemoryContractAdapter——薄适配器，包装现有模块满足 MemoryContract Protocol。

不做存储重构，仅委托给 StateManager / IndexManager / ScratchpadManager 等。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .chapter_commit_service import ChapterCommitService
from .commit_artifacts import extraction_list
from .config import DataModulesConfig, get_config
from .context_budget import enforce_budget
from .memory_contract import (
    CommitResult,
    ContextPack,
    EntitySnapshot,
    OpenLoop,
    Rule,
    TimelineEvent,
)
from .story_runtime_sources import load_runtime_sources
from .urgency_utils import coerce_urgency

logger = logging.getLogger(__name__)


def read_prev_chapter_tail(project_root: Path | str, chapter: int, chars: int) -> str:
    """上一章定稿正文尾段原文（W1/R1）。

    双布局：v7 `定稿/正文/NNNN-*.md` 优先，回退 v6 `正文/第NNNN章*.md`
    （chapter_paths.find_chapter_file，含卷布局）。front matter 剥离，
    返回「……」前缀的尾段；无正文返回空串。
    """
    root = Path(project_root)
    prev = max(1, int(chapter) - 1)
    body_path: Path | None = None
    v7_dir = root / "定稿" / "正文"
    if v7_dir.is_dir():
        matches = sorted(v7_dir.glob(f"{prev:04d}-*.md"))
        if matches:
            body_path = matches[0]
    if body_path is None:
        try:
            from chapter_paths import find_chapter_file

            body_path = find_chapter_file(root, prev)
        except Exception as exc:  # pragma: no cover - scripts 布局缺失时降级
            logger.debug("read_prev_chapter_tail: chapter_paths unavailable: %s", exc)
    if body_path is None or not Path(body_path).is_file():
        return ""
    text = Path(body_path).read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            text = parts[2]
    text = text.strip()
    if not text:
        return ""
    keep = max(0, int(chars))
    if keep == 0:
        return ""
    return "……" + text[-keep:]


class MemoryContractAdapter:
    """满足 MemoryContract Protocol 的具体实现。"""

    def __init__(self, config: DataModulesConfig | None = None):
        self.config = config or get_config()

    # ------------------------------------------------------------------
    # 内部懒加载（避免在构造时就初始化所有重量级模块）
    # ------------------------------------------------------------------

    def _state_manager(self):
        from .state_manager import StateManager
        return StateManager(self.config)

    def _index_manager(self):
        from .index_manager import IndexManager
        return IndexManager(self.config)

    def _memory_writer(self):
        from .memory.writer import MemoryWriter
        return MemoryWriter(self.config)

    def _memory_store(self):
        from .memory.store import ScratchpadManager
        return ScratchpadManager(self.config)

    def _memory_orchestrator(self):
        from .memory.orchestrator import MemoryOrchestrator
        return MemoryOrchestrator(self.config)

    # ------------------------------------------------------------------
    # 契约方法
    # ------------------------------------------------------------------

    def commit_chapter(self, chapter: int, result: dict) -> CommitResult:
        if self._should_use_commit_mainline(result):
            return self._commit_chapter_mainline(chapter, result)

        return self._commit_chapter_legacy(chapter, result)

    def _commit_chapter_legacy(self, chapter: int, result: dict) -> CommitResult:
        warnings: List[str] = []
        entities_added = 0
        entities_updated = 0
        state_changes_recorded = 0
        relationships_added = 0
        memory_items_added = 0
        summary_path = ""

        # 1. StateManager: process_chapter_result
        try:
            sm = self._state_manager()
            sm._load_state()
            sm_warnings = sm.process_chapter_result(chapter, result)
            warnings.extend(sm_warnings or [])
            entities_added = len(result.get("entities_new", []) or [])
            entities_updated = len(result.get("entities_appeared", []) or [])
            state_changes_recorded = len(result.get("state_changes", []) or [])
            relationships_added = len(result.get("relationships_new", []) or [])
        except Exception as e:
            logger.warning("commit_chapter: StateManager failed: %s", e)
            warnings.append(f"StateManager error: {e}")

        # 2. MemoryWriter: update_from_chapter_result
        try:
            mw = self._memory_writer()
            mem_stats = mw.update_from_chapter_result(chapter, result)
            memory_items_added = mem_stats.get("items_added", 0)
            if mem_stats.get("warnings"):
                warnings.extend(mem_stats["warnings"])
        except Exception as e:
            logger.warning("commit_chapter: MemoryWriter failed: %s", e)
            warnings.append(f"MemoryWriter error: {e}")

        # 3. 摘要路径
        padded = f"{chapter:04d}"
        summary_file = self.config.webnovel_dir / "summaries" / f"ch{padded}.md"
        if summary_file.exists():
            summary_path = str(summary_file)

        return CommitResult(
            chapter=chapter,
            entities_added=entities_added,
            entities_updated=entities_updated,
            state_changes_recorded=state_changes_recorded,
            relationships_added=relationships_added,
            memory_items_added=memory_items_added,
            summary_path=summary_path,
            warnings=warnings,
        )

    def _commit_chapter_mainline(self, chapter: int, result: dict) -> CommitResult:
        service = ChapterCommitService(self.config.project_root)
        payload = service.build_commit(
            chapter=chapter,
            review_result=result.get("review_result", {}) or {},
            fulfillment_result=result.get("fulfillment_result", {}) or {},
            disambiguation_result=result.get("disambiguation_result", {}) or {},
            extraction_result=result.get("extraction_result", {}) or {},
        )
        service.persist_commit(payload)
        if payload["meta"]["status"] == "accepted":
            payload = service.apply_projections(payload)

        summary_file = self.config.webnovel_dir / "summaries" / f"ch{chapter:04d}.md"
        return CommitResult(
            chapter=chapter,
            entities_added=len(extraction_list(payload, "entity_deltas")),
            entities_updated=0,
            state_changes_recorded=len(extraction_list(payload, "state_deltas")),
            relationships_added=0,
            memory_items_added=0,
            summary_path=str(summary_file) if summary_file.exists() else "",
            warnings=[f"commit_status={payload['meta']['status']}"],
        )

    def _should_use_commit_mainline(self, result: dict) -> bool:
        if not isinstance(result, dict):
            return False
        mainline_keys = {
            "review_result",
            "fulfillment_result",
            "disambiguation_result",
            "extraction_result",
        }
        return any(key in result for key in mainline_keys)

    def load_context(self, chapter: int, budget_tokens: int | None = None) -> ContextPack:
        sections: Dict[str, Any] = {}
        runtime_sources = load_runtime_sources(self.config.project_root, chapter)

        sections["story_contracts"] = dict(runtime_sources.contracts)
        # B3 去重：合同全文只在 story_contracts 出现一份；commit 只在 runtime_status
        # 保留一份（latest 与 accepted 相同时 accepted 侧降级为章号标记）。
        latest_commit = runtime_sources.latest_commit or {}
        latest_accepted = runtime_sources.latest_accepted_commit or {}
        runtime_status: Dict[str, Any] = {
            "chapter": runtime_sources.chapter,
            "fallback_sources": list(runtime_sources.fallback_sources),
            "primary_write_source": runtime_sources.primary_write_source,
        }
        if latest_commit:
            runtime_status["latest_commit"] = latest_commit
        if latest_accepted and latest_accepted != latest_commit:
            runtime_status["latest_accepted_commit"] = latest_accepted
        elif latest_accepted:
            runtime_status["latest_accepted_chapter"] = (latest_accepted.get("meta") or {}).get(
                "chapter"
            )
        sections["runtime_status"] = runtime_status

        # 1. MemoryOrchestrator 基础包
        try:
            orch = self._memory_orchestrator()
            pack = orch.build_memory_pack(chapter)
            sections["memory_pack"] = pack
        except Exception as e:
            logger.warning("load_context: orchestrator failed: %s", e)

        # 2. 章纲摘要
        try:
            from chapter_outline_loader import load_chapter_outline
            outline = load_chapter_outline(self.config.project_root, chapter, max_chars=1500)
            if outline and not outline.startswith("⚠️"):
                sections["outline"] = outline
        except Exception as e:
            logger.warning("load_context: outline failed: %s", e)

        # 3. 最近摘要（R10/F-11：新章优先组装——ch-1 在前，配额截断时 ch-2 先承受截断）
        try:
            summaries = {}
            for prev_ch in range(chapter - 1, max(1, chapter - 2) - 1, -1):
                text = self.read_summary(prev_ch)
                if text:
                    summaries[f"ch{prev_ch:04d}"] = text[:500]
            if summaries:
                sections["recent_summaries"] = summaries
        except Exception as e:
            logger.warning("load_context: summaries failed: %s", e)

        # W1/R1：上一章原文尾段（语气/钩子连续性第一手依据；PROTECTED，不参与整体丢弃）
        try:
            tail_chars = int(getattr(self.config, "context_prev_chapter_tail_chars", 1600) or 1600)
            tail = read_prev_chapter_tail(self.config.project_root, chapter, tail_chars)
            if tail:
                sections["prev_chapter_tail"] = tail
        except Exception as e:
            logger.warning("load_context: prev_chapter_tail failed: %s", e)

        # W1/F-11 增强：stale_notes 前置段（作者已改未消费提醒，context-agent 任务书前置消费）
        try:
            from .author_journal import unconsumed_stale

            stale = unconsumed_stale(self.config.project_root)
            if stale:
                sections["stale_notes"] = stale[:10]
        except Exception as e:
            logger.warning("load_context: stale_notes failed: %s", e)

        # 4. 主角状态 + 进度
        try:
            sm = self._state_manager()
            sm._load_state()
            protagonist = sm._state.get("protagonist_state")
            if protagonist:
                sections["protagonist"] = protagonist
            progress = sm._state.get("progress")
            if progress:
                sections["progress"] = progress
        except Exception as e:
            logger.warning("load_context: state failed: %s", e)

        # 5. 活跃约束（world_rules 前 5 条）
        try:
            rules = self.query_rules()
            if rules:
                sections["active_rules"] = [r.to_dict() for r in rules[:5]]
        except Exception as e:
            logger.warning("load_context: rules failed: %s", e)

        # 6. 紧急伏笔（前 3 条）
        try:
            loops = self.get_open_loops()
            if loops:
                sections["urgent_loops"] = [l.to_dict() for l in loops[:3]]
        except Exception as e:
            logger.warning("load_context: loops failed: %s", e)

        # 7. 题材画像摘要（只抽取当前题材的 profile，避免全量加载 genre-profiles.md）
        try:
            from .genre_profile_builder import extract_genre_section
            genre = str(
                (sections.get("story_contracts", {}).get("master", {})
                 .get("route", {}).get("primary_genre", ""))
                or sections.get("protagonist", {}).get("genre", "")
                or ""
            ).strip()
            if not genre:
                sm = self._state_manager()
                sm._load_state()
                project_info = sm._state.get("project_info", {}) or {}
                legacy_project = sm._state.get("project", {}) or {}
                genre = str(
                    project_info.get("genre")
                    or project_info.get("genre_label")
                    or legacy_project.get("genre")
                    or ""
                ).strip()
            if genre:
                profile_path = self.config.project_root / ".claude" / "references" / "genre-profiles.md"
                if profile_path.exists():
                    profile_text = profile_path.read_text(encoding="utf-8")
                    excerpt = extract_genre_section(profile_text, genre)
                    if excerpt:
                        sections["genre_profile_excerpt"] = excerpt
        except Exception as e:
            logger.warning("load_context: genre_profile_excerpt failed: %s", e)

        # 8. 作者文风记忆（/webnovel-learn 写入的 project_memory.json）
        try:
            patterns = self._load_author_style_patterns()
            if patterns:
                sections["author_style_patterns"] = patterns
        except Exception as e:
            logger.warning("load_context: author_style_patterns failed: %s", e)

        # 9. 风格契约（设定集/风格契约.md，作者手写的文风约定）
        try:
            contract = self._load_style_contract()
            if contract:
                sections["style_contract"] = contract
        except Exception as e:
            logger.warning("load_context: style_contract failed: %s", e)

        # S1/C1：section 配额 + 总预算执行（硬约束类 section 永不整体丢弃）
        total = (
            int(budget_tokens)
            if budget_tokens is not None
            else int(getattr(self.config, "context_load_total_budget", 20000) or 20000)
        )
        sections, budget_stats = enforce_budget(sections, total_budget=total)

        return ContextPack(
            chapter=chapter,
            sections=sections,
            budget_used_tokens=budget_stats["used"],
        )

    _STYLE_PATTERNS_LIMIT = 10
    _STYLE_PATTERN_DESC_MAX_CHARS = 200
    _STYLE_CONTRACT_MAX_CHARS = 2000

    @staticmethod
    def _importance_weight(value: Any) -> float:
        """importance 归一为数值权重（越大越重要）；兼容命名档位与数字字符串。"""
        named = {
            "critical": 5.0,
            "highest": 5.0,
            "high": 4.0,
            "medium": 3.0,
            "normal": 3.0,
            "low": 2.0,
            "lowest": 1.0,
        }
        raw = str(value if value is not None else "").strip().lower()
        if raw in named:
            return named[raw]
        try:
            return float(raw)
        except ValueError:
            return named["medium"]

    def _load_author_style_patterns(self) -> List[Dict[str, Any]]:
        memory_path = self.config.webnovel_dir / "project_memory.json"
        if not memory_path.exists():
            return []
        try:
            data = json.loads(memory_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.warning("project_memory.json 解析失败，跳过: %s", e)
            return []
        patterns = data.get("patterns") if isinstance(data, dict) else None
        if not isinstance(patterns, list):
            return []
        valid = [p for p in patterns if isinstance(p, dict) and str(p.get("description", "")).strip()]
        valid.sort(key=lambda p: self._importance_weight(p.get("importance")), reverse=True)
        result = []
        for p in valid[: self._STYLE_PATTERNS_LIMIT]:
            item: Dict[str, Any] = {
                "pattern_type": str(p.get("pattern_type", "other")),
                "description": str(p["description"])[: self._STYLE_PATTERN_DESC_MAX_CHARS],
            }
            if p.get("source_chapter") is not None:
                item["source_chapter"] = p["source_chapter"]
            result.append(item)
        return result

    def _load_style_contract(self) -> str:
        path = self.config.settings_dir / "风格契约.md"
        if not path.exists():
            matches = sorted(self.config.settings_dir.glob("*风格契约*.md")) if self.config.settings_dir.exists() else []
            if not matches:
                return ""
            path = matches[0]
        text = path.read_text(encoding="utf-8").strip()
        return text[: self._STYLE_CONTRACT_MAX_CHARS]

    def query_entity(self, entity_id: str) -> Optional[EntitySnapshot]:
        try:
            sm = self._state_manager()
            sm._load_state()
            entity = sm.get_entity(entity_id)
            if not entity:
                return None

            entity_type = sm.get_entity_type(entity_id) or "角色"
            state_changes = sm.get_state_changes(entity_id)
            recent_changes = state_changes[-5:] if state_changes else []

            return EntitySnapshot(
                id=entity_id,
                name=entity.get("name", entity_id),
                type=entity_type,
                tier=entity.get("tier", "核心"),
                aliases=entity.get("aliases", []),
                attributes={k: v for k, v in entity.items()
                            if k not in ("name", "tier", "aliases", "first_appearance", "last_appearance")},
                first_appearance=entity.get("first_appearance", 0),
                last_appearance=entity.get("last_appearance", 0),
                recent_state_changes=recent_changes,
            )
        except Exception as e:
            logger.warning("query_entity(%s) failed: %s", entity_id, e)
            return None

    def query_rules(self, domain: str = "") -> List[Rule]:
        try:
            store = self._memory_store()
            items = store.query(category="world_rule", status="active")
            rules = []
            for item in items:
                if domain and item.subject != domain and domain not in item.value:
                    continue
                rules.append(Rule(
                    id=item.id,
                    subject=item.subject,
                    field=item.field,
                    value=item.value,
                    domain=item.subject,
                    source_chapter=item.source_chapter,
                ))
            return rules
        except Exception as e:
            logger.warning("query_rules failed: %s", e)
            return []

    def read_summary(self, chapter: int) -> str:
        padded = f"{chapter:04d}"
        summary_file = self.config.webnovel_dir / "summaries" / f"ch{padded}.md"
        try:
            if summary_file.exists():
                return summary_file.read_text(encoding="utf-8")
            return ""
        except Exception as e:
            logger.warning("read_summary(%d) failed: %s", chapter, e)
            return ""

    def get_open_loops(self, status: str = "active") -> List[OpenLoop]:
        try:
            store = self._memory_store()
            items = store.query(category="open_loop", status=status)
            return [
                OpenLoop(
                    id=item.id,
                    content=item.value,
                    status=item.status,
                    planted_chapter=item.source_chapter,
                    expected_payoff=item.payload.get("expected_payoff", ""),
                    urgency=coerce_urgency(item.payload.get("urgency")),
                )
                for item in items
            ]
        except Exception as e:
            logger.warning("get_open_loops failed: %s", e)
            return []

    def get_timeline(self, from_ch: int, to_ch: int) -> List[TimelineEvent]:
        try:
            store = self._memory_store()
            items = store.query(category="timeline", status="active")
            events = []
            for item in items:
                ch = item.source_chapter
                if from_ch <= ch <= to_ch:
                    events.append(TimelineEvent(
                        event=item.value,
                        chapter=ch,
                        time_hint=item.field,
                        event_type=item.subject,
                    ))
            events.sort(key=lambda e: e.chapter)
            return events
        except Exception as e:
            logger.warning("get_timeline failed: %s", e)
            return []
