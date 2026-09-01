#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scratchpad 持久化与查询。
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import DataModulesConfig, get_config
from ..cli_output import print_error, print_success
from ..cli_args import normalize_global_project_root, load_json_arg

from .schema import (
    BUCKET_TO_CATEGORY,
    CATEGORY_KEY_RULES,
    CATEGORY_TO_BUCKET,
    FACT_CATEGORIES,
    VALID_STATUSES,
    MemoryItem,
    ScratchpadData,
    memory_item_key,
    now_iso,
)

try:
    from security_utils import atomic_write_json, read_json_safe
except ImportError:  # pragma: no cover
    from scripts.security_utils import atomic_write_json, read_json_safe

from filelock import FileLock


class ScratchpadManager:
    def __init__(self, config: DataModulesConfig | None = None):
        self.config = config or get_config()
        self.path = Path(self.config.scratchpad_file)
        self._lock = FileLock(str(self.path) + ".lock", timeout=30)

    def load(self) -> ScratchpadData:
        if not self.path.exists():
            return ScratchpadData.empty()
        payload = read_json_safe(self.path, default={})
        if not isinstance(payload, dict):
            return ScratchpadData.empty()
        return ScratchpadData.from_dict(payload)

    def save(self, data: ScratchpadData, _use_lock: bool = True) -> None:
        self.config.ensure_dirs()
        if bool(getattr(self.config, "memory_compactor_enabled", True)):
            threshold = max(1, int(getattr(self.config, "memory_compactor_threshold", 500)))
            if data.count_items() > threshold:
                from .compactor import compact_scratchpad

                data = compact_scratchpad(data, max_items=threshold)
        payload = data.to_dict()
        payload.setdefault("meta", {})
        payload["meta"]["last_updated"] = now_iso()
        payload["meta"]["total_items"] = data.count_items()
        atomic_write_json(self.path, payload, use_lock=_use_lock, backup=True)

    def _key_for(self, item: MemoryItem) -> tuple[Any, ...]:
        return memory_item_key(item)

    def _merge_into(self, data: ScratchpadData, normalized: MemoryItem) -> Dict[str, int]:
        """把单条目合并进已加载的数据（不落盘）；upsert_item/upsert_items 共用。"""
        bucket = CATEGORY_TO_BUCKET[normalized.category]
        rows: List[MemoryItem] = list(getattr(data, bucket))
        target_key = self._key_for(normalized)

        outdated = 0
        contradicted = 0
        replaced_existing = False
        new_rows: List[MemoryItem] = []
        for row in rows:
            row_key = self._key_for(row)
            if row_key == target_key and row.id != normalized.id:
                if normalized.status == "tentative":
                    # P1-3：tentative 候选不降级现有值（含 active），
                    # 仅并存记录，等待确认（memory correct --status active）
                    replaced_existing = True
                    new_rows.append(row)
                    continue
                if row.status == "active":
                    old_value = str(row.value or "").strip()
                    new_value = str(normalized.value or "").strip()
                    if (
                        normalized.category in FACT_CATEGORIES
                        and old_value
                        and new_value
                        and old_value != new_value
                    ):
                        # P1-3：事实类同 key 出现不同值 → 矛盾嫌疑，
                        # 旧值标 contradicted（保留审计轨迹，conflicts 可透出）
                        row = MemoryItem(**{**asdict(row), "status": "contradicted", "updated_at": now_iso()})
                        contradicted += 1
                    else:
                        # 同 key 旧值降级为 outdated，保留审计轨迹
                        row = MemoryItem(**{**asdict(row), "status": "outdated", "updated_at": now_iso()})
                        outdated += 1
                elif row.status not in {"outdated", "contradicted"}:
                    row = MemoryItem(**{**asdict(row), "status": "outdated", "updated_at": now_iso()})
                    outdated += 1
                replaced_existing = True
            elif row.id == normalized.id:
                replaced_existing = True
                continue
            new_rows.append(row)

        normalized.updated_at = normalized.updated_at or now_iso()
        new_rows.append(normalized)
        setattr(data, bucket, new_rows)
        return {
            "added": 0 if replaced_existing else 1,
            "updated": 1 if replaced_existing else 0,
            "outdated": outdated,
            "contradicted": contradicted,
        }

    def upsert_item(self, item: MemoryItem) -> Dict[str, int]:
        normalized = item.normalized()
        with self._lock:
            data = self.load()
            result = self._merge_into(data, normalized)
            self.save(data, _use_lock=False)
        return result

    def upsert_items(self, items: List[MemoryItem]) -> Dict[str, int]:
        """批量 upsert（增量审阅 P3-22a）：一次 load/save，按序应用同 upsert_item 语义。"""
        total = {"added": 0, "updated": 0, "outdated": 0, "contradicted": 0}
        if not items:
            return total
        with self._lock:
            data = self.load()
            for item in items:
                counts = self._merge_into(data, item.normalized())
                for key in total:
                    total[key] += counts[key]
            self.save(data, _use_lock=False)
        return total

    def mark_status(self, item_id: str, status: str) -> bool:
        if not item_id:
            return False
        with self._lock:
            data = self.load()
            updated = False
            for bucket in BUCKET_TO_CATEGORY:
                rows: List[MemoryItem] = getattr(data, bucket)
                for i, row in enumerate(rows):
                    if row.id == item_id:
                        rows[i] = MemoryItem(**{**asdict(row), "status": status, "updated_at": now_iso()})
                        updated = True
            if updated:
                self.save(data, _use_lock=False)
        return updated

    def correct(
        self,
        *,
        item_id: Optional[str] = None,
        category: Optional[str] = None,
        subject: Optional[str] = None,
        field: Optional[str] = None,
        value: Optional[str] = None,
        status: Optional[str] = None,
        delete: bool = False,
    ) -> Dict[str, Any]:
        """纠错：按 id 或 (category, subject[, field]) 定位条目，修正内容字段、
        调整状态或删除错误条目。返回变更摘要供 CLI 输出。

        写前校验：定位方式 item_id 与 category+subject 至少给其一；
        非删除时 value / status 至少给其一。
        """
        result: Dict[str, Any] = {
            "matched": 0,
            "updated": 0,
            "deleted": 0,
            "not_found": False,
        }
        if not item_id and not (category and subject):
            result["error"] = "missing_locator"
            result["hint"] = "provide --id or (--category + --subject)"
            return result
        if not delete and value is None and status is None:
            result["error"] = "nothing_to_change"
            result["hint"] = "provide --value / --status / --delete"
            return result
        if status is not None and status not in VALID_STATUSES:
            result["error"] = "invalid_status"
            result["hint"] = f"status must be one of {sorted(VALID_STATUSES)}"
            return result

        with self._lock:
            data = self.load()
            for bucket in BUCKET_TO_CATEGORY:
                rows: List[MemoryItem] = getattr(data, bucket)
                new_rows: List[MemoryItem] = []
                for row in rows:
                    hit = self._matches(row, item_id, category, subject, field)
                    if not hit:
                        new_rows.append(row)
                        continue
                    result["matched"] += 1
                    if delete:
                        result["deleted"] += 1
                        continue
                    updated = dict(asdict(row))
                    if value is not None:
                        updated["value"] = str(value)
                    if status is not None:
                        updated["status"] = status
                    updated["updated_at"] = now_iso()
                    new_rows.append(MemoryItem(**updated))
                    result["updated"] += 1
                setattr(data, bucket, new_rows)
            if result["matched"] == 0:
                result["not_found"] = True
            else:
                self.save(data, _use_lock=False)
        return result

    @staticmethod
    def _matches(
        row: MemoryItem,
        item_id: Optional[str],
        category: Optional[str],
        subject: Optional[str],
        field: Optional[str],
    ) -> bool:
        if item_id:
            return row.id == item_id
        if category and row.category != category:
            return False
        if subject and row.subject != subject:
            return False
        if field and row.field != field:
            return False
        return True

    def query(
        self,
        category: Optional[str] = None,
        subject: Optional[str] = None,
        status: Optional[str] = "active",
    ) -> List[MemoryItem]:
        data = self.load()
        categories = [category] if category else list(CATEGORY_TO_BUCKET.keys())
        result: List[MemoryItem] = []
        for cat in categories:
            bucket = CATEGORY_TO_BUCKET.get(cat)
            if not bucket:
                continue
            rows: List[MemoryItem] = getattr(data, bucket)
            for row in rows:
                if subject and row.subject != subject:
                    continue
                if status and row.status != status:
                    continue
                result.append(row)
        return result

    def stats(self) -> Dict[str, Any]:
        data = self.load()
        by_category: Dict[str, int] = {}
        active = 0
        outdated = 0
        contradicted = 0
        tentative = 0
        for category, bucket in CATEGORY_TO_BUCKET.items():
            rows: List[MemoryItem] = getattr(data, bucket)
            by_category[category] = len(rows)
            for row in rows:
                if row.status == "active":
                    active += 1
                elif row.status == "outdated":
                    outdated += 1
                elif row.status == "contradicted":
                    contradicted += 1
                elif row.status == "tentative":
                    tentative += 1
        return {
            "total": data.count_items(),
            "active": active,
            "outdated": outdated,
            "contradicted": contradicted,
            "tentative": tentative,
            "by_category": by_category,
            "path": str(self.path),
        }

    def dump(self) -> Dict[str, Any]:
        return self.load().to_dict()

    def conflicts(self) -> List[Dict[str, Any]]:
        data = self.load()
        conflicts: List[Dict[str, Any]] = []
        for category, bucket in CATEGORY_TO_BUCKET.items():
            key_count: Dict[tuple[Any, ...], int] = {}
            rows: List[MemoryItem] = getattr(data, bucket)
            for row in rows:
                # P1-3：contradicted 条目本身就是一次已检测到的矛盾，
                # 直接透出为冲突信号（orchestrator warnings 消费）
                if row.status == "contradicted":
                    conflicts.append(
                        {
                            "category": category,
                            "key": list(self._key_for(row)),
                            "status": "contradicted",
                            "value": str(row.value or "")[:60],
                            "source_chapter": row.source_chapter,
                        }
                    )
                    continue
                if row.status != "active":
                    continue
                key = self._key_for(row)
                key_count[key] = key_count.get(key, 0) + 1
            for key, cnt in key_count.items():
                if cnt > 1:
                    conflicts.append({"category": category, "key": list(key), "active_items": cnt})
        return conflicts


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Memory Scratchpad CLI")
    parser.add_argument("--project-root", type=str, help="项目根目录")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("stats")
    p_query = sub.add_parser("query")
    p_query.add_argument("--category", type=str, default=None)
    p_query.add_argument("--subject", type=str, default=None)
    p_query.add_argument("--status", type=str, default="active")
    sub.add_parser("dump")
    sub.add_parser("conflicts")

    p_update = sub.add_parser("update")
    p_update.add_argument("--chapter", type=int, required=True)
    p_update.add_argument("--data", required=True, help="章节结构化结果 JSON")

    p_correct = sub.add_parser("correct", help="修正已入库记忆条目（改内容/状态/删除）")
    p_correct.add_argument("--id", dest="item_id", default=None, help="按条目 id 精确定位")
    p_correct.add_argument("--category", type=str, default=None, help="按分类过滤（需与 --subject 搭配）")
    p_correct.add_argument("--subject", type=str, default=None, help="按主体过滤（需与 --category 搭配）")
    p_correct.add_argument("--field", type=str, default=None, help="按字段进一步收窄")
    p_correct.add_argument("--value", type=str, default=None, help="修正后的内容值")
    p_correct.add_argument("--status", type=str, default=None, help=f"调整状态：{sorted(VALID_STATUSES)}")
    p_correct.add_argument("--delete", action="store_true", help="删除匹配条目")

    sub.add_parser("bootstrap")

    args = parser.parse_args(normalize_global_project_root(sys.argv[1:]))

    config = None
    if args.project_root:
        from project_locator import resolve_project_root

        resolved_root = resolve_project_root(args.project_root)
        config = DataModulesConfig.from_project_root(resolved_root)

    manager = ScratchpadManager(config)

    if args.command == "stats":
        print_success(manager.stats(), message="memory_stats")
        return
    if args.command == "dump":
        print_success(manager.dump(), message="memory_dump")
        return
    if args.command == "conflicts":
        print_success(manager.conflicts(), message="memory_conflicts")
        return
    if args.command == "query":
        rows = [row.to_dict() for row in manager.query(args.category, args.subject, args.status)]
        print_success(rows, message="memory_query")
        return
    if args.command == "update":
        from .writer import MemoryWriter

        resolved_config = config or get_config()
        payload = load_json_arg(args.data, base_dir=resolved_config.project_root)
        writer = MemoryWriter(resolved_config)
        result = writer.update_from_chapter_result(args.chapter, payload)
        print_success(result, message="memory_updated")
        return
    if args.command == "correct":
        result = manager.correct(
            item_id=args.item_id,
            category=args.category,
            subject=args.subject,
            field=args.field,
            value=args.value,
            status=args.status,
            delete=bool(args.delete),
        )
        if result.get("error"):
            print_error(result["error"], "记忆纠错失败", suggestion=result.get("hint"))
            sys.exit(1)
        print_success(result, message="memory_corrected")
        return
    if args.command == "bootstrap":
        from .bootstrap import bootstrap_from_index

        result = bootstrap_from_index(config or get_config())
        print_success(result, message="memory_bootstrapped")
        return

    print_error("UNKNOWN_COMMAND", "未知命令", suggestion="请查看 --help")
