#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import filelock

from .commit_artifacts import extraction_dict, extraction_list, extraction_text
from .story_contracts import read_json_if_exists

try:
    from chapter_paths import find_chapter_file
except ImportError:  # pragma: no cover
    from scripts.chapter_paths import find_chapter_file

try:
    from security_utils import atomic_write_json
except ImportError:  # pragma: no cover
    from scripts.security_utils import atomic_write_json


class _LockedState:
    def __init__(self, state_path: Path, lock_path: Path):
        self.state_path = state_path
        self.lock_path = lock_path
        self.state: dict[str, Any] = {}
        self._lock: filelock.FileLock | None = None

    def __enter__(self) -> dict[str, Any]:
        self._lock = filelock.FileLock(str(self.lock_path), timeout=10)
        self._lock.acquire()
        self.state = read_json_if_exists(self.state_path) or {}
        return self.state

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if exc_type is None:
                atomic_write_json(self.state_path, self.state, use_lock=False, backup=True)
        finally:
            if self._lock is not None:
                self._lock.release()
        return False


class StateProjectionWriter:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.state_path = self.project_root / ".webnovel" / "state.json"
        self.lock_path = self.state_path.with_suffix(self.state_path.suffix + ".lock")

    def apply(self, commit_payload: dict) -> dict:
        chapter = int(commit_payload.get("meta", {}).get("chapter") or 0)
        status = commit_payload["meta"]["status"]

        if status == "rejected":
            if chapter > 0:
                with self._locked_state() as state:
                    progress = state.setdefault("progress", {})
                    chapter_status = progress.setdefault("chapter_status", {})
                    chapter_status[str(chapter)] = "chapter_rejected"
            return {"applied": True, "writer": "state", "reason": "commit_rejected_status_updated"}

        if status != "accepted":
            return {"applied": False, "writer": "state", "reason": f"unknown_status:{status}"}

        with self._locked_state() as state:
            entity_state = state.setdefault("entity_state", {})
            progress = state.setdefault("progress", {})
            chapter_status = progress.setdefault("chapter_status", {})

            protagonist_ids = self._collect_protagonist_ids(commit_payload, state)

            applied_count = 0
            for delta in self._collect_state_deltas(commit_payload):
                entity_id = str(delta.get("entity_id") or "").strip()
                field = str(delta.get("field") or "").strip()
                if not entity_id or not field:
                    continue
                new_value = delta.get("new")
                entity_bucket = entity_state.setdefault(entity_id, {})
                self._set_path(entity_bucket, field, new_value)
                if entity_id in protagonist_ids:
                    self._set_path(state.setdefault("protagonist_state", {}), field, new_value)
                applied_count += 1

            if chapter > 0:
                old_current = self._safe_int(progress.get("current_chapter"))
                old_total = self._safe_int(progress.get("total_words"))
                old_status = chapter_status.get(str(chapter))

                chapter_status[str(chapter)] = "chapter_committed"
                progress["current_chapter"] = max(old_current, chapter)

                projected_total = self._project_total_words(chapter_status)
                if projected_total > 0:
                    progress["total_words"] = projected_total
                else:
                    progress["total_words"] = old_total

                if (
                    old_status != "chapter_committed"
                    or progress.get("current_chapter") != old_current
                    or progress.get("total_words") != old_total
                ):
                    progress["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            strand_applied = self._apply_strand_tracker(state, chapter, commit_payload)
            foreshadow_applied = self._apply_foreshadowing(state, chapter, commit_payload)

        return {
            "applied": applied_count > 0 or chapter > 0,
            "writer": "state",
            "applied_count": applied_count,
            "strand_tracker": strand_applied,
            "foreshadowing": foreshadow_applied,
        }

    def _locked_state(self):
        return _LockedState(self.state_path, self.lock_path)

    def _collect_state_deltas(self, commit_payload: dict) -> list[dict]:
        deltas = [
            self._normalize_state_delta(delta)
            for delta in extraction_list(commit_payload, "state_deltas")
            if isinstance(delta, dict)
        ]
        seen = {
            (str(delta.get("entity_id") or "").strip(), str(delta.get("field") or "").strip())
            for delta in deltas
        }

        for event in extraction_list(commit_payload, "accepted_events"):
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("event_type") or "").strip()
            payload = dict(event.get("payload") or {})
            entity_id = str(payload.get("entity_id") or event.get("subject") or "").strip()
            if not entity_id:
                continue

            field = ""
            if event_type == "power_breakthrough":
                field = (
                    str(payload.get("field") or payload.get("field_path") or "realm").strip()
                )
            elif event_type == "character_state_changed":
                field = str(payload.get("field") or payload.get("field_path") or "").strip()
            else:
                continue

            key = (entity_id, field)
            if not field or key in seen:
                continue

            seen.add(key)
            deltas.append(
                {
                    "entity_id": entity_id,
                    "field": field,
                    "old": (
                        payload.get("old")
                        if "old" in payload
                        else payload.get("from")
                        if "from" in payload
                        else payload.get("old_value")
                        if "old_value" in payload
                        else payload.get("previous_state")
                    ),
                    "new": (
                        payload.get("new")
                        if "new" in payload
                        else payload.get("to")
                        if "to" in payload
                        else payload.get("new_value")
                        if "new_value" in payload
                        else payload.get("new_state")
                    ),
                }
            )
        return deltas

    @staticmethod
    def _normalize_state_delta(delta: dict) -> dict:
        """统一 state_delta 字段名：field/field_path → field, new/new_value → new."""
        result = dict(delta)
        if "field" not in result and "field_path" in result:
            result["field"] = result["field_path"]
        if "new" not in result and "new_value" in result:
            result["new"] = result["new_value"]
        if "old" not in result and "old_value" in result:
            result["old"] = result["old_value"]
        return result

    @staticmethod
    def _set_path(target: dict, path: str, value: Any) -> None:
        """支持点号路径写入嵌套字典：'power.realm' → target['power']['realm']=value。"""
        if not isinstance(target, dict) or not path:
            return
        if "." not in path:
            target[path] = value
            return
        parts = path.split(".")
        cursor = target
        for part in parts[:-1]:
            nxt = cursor.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cursor[part] = nxt
            cursor = nxt
        cursor[parts[-1]] = value

    def _collect_protagonist_ids(self, commit_payload: dict, state: dict) -> set[str]:
        """聚合本次 commit + state.json 中已知的主角实体 ID。

        识别信号（任一命中即视为主角）：
        - entity_deltas 子项 `is_protagonist: true`
        - entity_deltas 子项 `tier == "主角"`
        - entity_deltas 的 canonical_name 与 state.protagonist_state.name 相同
        - state.protagonist_state.entity_id 已经被显式设置过
        """
        ids: set[str] = set()

        protagonist_state = state.get("protagonist_state") or {}
        existing_eid = str(protagonist_state.get("entity_id") or "").strip()
        if existing_eid:
            ids.add(existing_eid)
        protagonist_name = str(protagonist_state.get("name") or "").strip()

        for delta in extraction_list(commit_payload, "entity_deltas"):
            if not isinstance(delta, dict):
                continue
            eid = str(delta.get("entity_id") or delta.get("id") or "").strip()
            if not eid:
                continue
            tier = str(delta.get("tier") or "").strip()
            canonical = str(
                delta.get("canonical_name")
                or (delta.get("payload") or {}).get("name")
                or ""
            ).strip()
            if (
                delta.get("is_protagonist")
                or tier == "主角"
                or (protagonist_name and canonical == protagonist_name)
            ):
                ids.add(eid)
        return ids

    def _apply_foreshadowing(self, state: dict, chapter: int, commit_payload: dict) -> int:
        """把 open_loop 事件聚合进 plot_threads.foreshadowing（issue #130）。

        幂等：created 按 content 去重；closed 对已 resolved 条目不重复改写，
        因此 projections replay 重放任意章节不会产生重复或抖动。
        """
        if chapter <= 0:
            return 0
        loop_events = [
            event
            for event in extraction_list(commit_payload, "accepted_events")
            if isinstance(event, dict)
            and str(event.get("event_type") or "").strip()
            in ("open_loop_created", "open_loop_closed", "promise_paid_off")
        ]
        if not loop_events:
            return 0

        plot_threads = state.get("plot_threads")
        if not isinstance(plot_threads, dict):
            plot_threads = {}
            state["plot_threads"] = plot_threads
        rows = plot_threads.get("foreshadowing")
        if not isinstance(rows, list):
            rows = []
            plot_threads["foreshadowing"] = rows

        applied = 0
        for event in loop_events:
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            content = str(
                payload.get("content")
                or payload.get("description")
                or event.get("subject")
                or ""
            ).strip()
            if not content:
                continue
            event_type = str(event.get("event_type") or "").strip()
            row = next(
                (
                    r
                    for r in rows
                    if isinstance(r, dict) and str(r.get("content") or "").strip() == content
                ),
                None,
            )
            if event_type == "open_loop_created":
                if row is not None:
                    row.setdefault("planted_chapter", chapter)
                    continue
                new_row: dict[str, Any] = {
                    "content": content,
                    "status": "active",
                    "planted_chapter": chapter,
                }
                target = self._safe_int(
                    payload.get("target_chapter") or payload.get("due_chapter")
                )
                if target > 0:
                    new_row["target_chapter"] = target
                tier = str(payload.get("tier") or "").strip()
                if tier:
                    new_row["tier"] = tier
                rows.append(new_row)
                applied += 1
            else:
                if row is None:
                    rows.append(
                        {
                            "content": content,
                            "status": "resolved",
                            "resolved_chapter": chapter,
                        }
                    )
                    applied += 1
                elif str(row.get("status") or "") != "resolved":
                    row["status"] = "resolved"
                    row["resolved_chapter"] = chapter
                    applied += 1
        return applied

    def _apply_strand_tracker(self, state: dict, chapter: int, commit_payload: dict) -> bool:
        strand = self._dominant_strand(commit_payload)
        if chapter <= 0 or not strand:
            return False

        tracker = state.get("strand_tracker")
        if not isinstance(tracker, dict):
            tracker = {}
            state["strand_tracker"] = tracker

        valid = ("quest", "fire", "constellation")
        for name in valid:
            tracker.setdefault(f"last_{name}_chapter", 0)
        tracker.setdefault("current_dominant", None)
        tracker.setdefault("chapters_since_switch", 0)

        history = tracker.get("history")
        if not isinstance(history, list):
            history = []

        replaced_strands = set()
        cleaned = []
        for row in history:
            if not isinstance(row, dict):
                continue
            row_chapter = self._safe_int(row.get("chapter"))
            row_strand = str(row.get("dominant") or "").strip().lower()
            if row_chapter <= 0 or row_strand not in valid:
                continue
            if row_chapter == chapter:
                replaced_strands.add(row_strand)
                continue
            cleaned.append({"chapter": row_chapter, "dominant": row_strand})
        cleaned.append({"chapter": chapter, "dominant": strand})
        cleaned.sort(key=lambda row: row["chapter"])
        if len(cleaned) > 50:
            cleaned = cleaned[-50:]
        tracker["history"] = cleaned

        for name in valid:
            history_last = max((row["chapter"] for row in cleaned if row["dominant"] == name), default=0)
            existing_last = 0 if name in replaced_strands else self._safe_int(tracker.get(f"last_{name}_chapter"))
            tracker[f"last_{name}_chapter"] = max(
                existing_last,
                history_last,
            )

        latest = cleaned[-1]
        current = latest["dominant"]
        tracker["current_dominant"] = current
        streak = 0
        for row in reversed(cleaned):
            if row["dominant"] != current:
                break
            streak += 1
        tracker["chapters_since_switch"] = streak
        return True

    def _dominant_strand(self, commit_payload: dict) -> str:
        chapter_meta = extraction_dict(commit_payload, "chapter_meta")
        raw = (
            extraction_text(commit_payload, "dominant_strand")
            or commit_payload.get("strand")
            or chapter_meta.get("dominant_strand")
            or chapter_meta.get("strand")
            or ""
        )
        strand = str(raw or "").strip().lower()
        return strand if strand in {"quest", "fire", "constellation"} else ""

    def _project_total_words(self, chapter_status: dict) -> int:
        total = 0
        for raw_chapter, raw_status in chapter_status.items():
            if raw_status != "chapter_committed":
                continue
            chapter = self._safe_int(raw_chapter)
            if chapter <= 0:
                continue
            chapter_file = find_chapter_file(self.project_root, chapter)
            if chapter_file is None:
                continue
            try:
                total += self._count_chapter_words(chapter_file.read_text(encoding="utf-8"))
            except OSError:
                continue
        return total

    def _count_chapter_words(self, content: str) -> int:
        text = re.sub(r"```[\s\S]*?```", "", content)
        text = re.sub(r"^#+ .*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"---", "", text)
        return len(text.strip())

    def _safe_int(self, value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
