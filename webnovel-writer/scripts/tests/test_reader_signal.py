#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T25（M5）反馈闭合测试（reading_power 投影 + reader_signal）。

对应方案：03 R4（F-05/F-06）、08 T25。
验收契约：accepted 提交投影后 chapter_reading_power 自动有记录（生产端闭合）；
连续两章同型钩子后第三章 reader_signal 含差异化提醒（消费端闭合）；
index get-reader-signals 含 review_trend。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def _commit_payload(chapter: int, *, hook_type: str = "危机钩", hook_strength: str = "strong") -> dict:
    return {
        "meta": {"chapter": chapter, "status": "accepted"},
        "extraction_result": {
            "summary_text": f"---\nchapter: {chapter:04d}\nhook_type: \"{hook_type}\"\nhook_strength: \"{hook_strength}\"\n---\n## 剧情摘要\n摘要",
            "accepted_events": [],
        },
    }


@pytest.fixture()
def root(tmp_path: Path):
    from data_modules.config import DataModulesConfig

    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    cfg.state_file.write_text("{}", encoding="utf-8")
    return tmp_path


class TestProduction:
    def test_writer_extracts_hook_from_summary_front_matter(self, root: Path):
        from data_modules.reading_power_projection import ReadingPowerProjectionWriter, extract_hook_fields

        assert extract_hook_fields({"hook_type": "悬念钩", "hook_strength": "weak"}) == ("悬念钩", "weak")
        writer = ReadingPowerProjectionWriter(root)
        result = writer.apply(_commit_payload(37))

        assert result["applied"] is True
        assert result["hook_type"] == "危机钩"

    def test_writer_skips_without_hook_fields(self, root: Path):
        from data_modules.reading_power_projection import ReadingPowerProjectionWriter

        payload = _commit_payload(38)
        payload["extraction_result"] = {"summary_text": "无 front matter 摘要", "accepted_events": []}
        result = ReadingPowerProjectionWriter(root).apply(payload)

        assert result["applied"] is False
        assert result["reason"] == "not_required"

    def test_projection_chain_persists_reading_power(self, root: Path):
        """T25 验收（生产端）：chapter-commit 投影后 chapter_reading_power 有自动写入。"""
        from data_modules.config import DataModulesConfig
        from data_modules.chapter_commit_service import ChapterCommitService
        from data_modules.index_manager import IndexManager

        service = ChapterCommitService(root)
        payload = service.apply_projections(_commit_payload(37))

        assert payload["projection_status"].get("reading_power") == "done"
        rows = IndexManager(DataModulesConfig.from_project_root(root)).get_recent_reading_power(5)
        assert any(row.get("chapter") == 37 and row.get("hook_type") == "危机钩" for row in rows)

    def test_rejected_commit_skips_reading_power(self, root: Path):
        from data_modules.chapter_commit_service import ChapterCommitService

        payload = _commit_payload(38)
        payload["meta"]["status"] = "rejected"
        payload = ChapterCommitService(root).apply_projections(payload)

        assert payload["projection_status"].get("reading_power") == "skipped"


class TestConsumption:
    def test_differentiation_reminder_after_two_same_hooks(self):
        from data_modules.reader_signal_builder import derive_differentiation_reminder

        recent = [
            {"chapter": 39, "hook_type": "危机钩"},
            {"chapter": 38, "hook_type": "危机钩"},
        ]
        reminder = derive_differentiation_reminder(recent)

        assert "危机钩" in reminder and "差异化" in reminder

    def test_no_reminder_for_varied_hooks(self):
        from data_modules.reader_signal_builder import derive_differentiation_reminder

        recent = [
            {"chapter": 39, "hook_type": "危机钩"},
            {"chapter": 38, "hook_type": "悬念钩"},
        ]
        assert derive_differentiation_reminder(recent) == ""

    def test_load_context_carries_reader_signal(self, root: Path):
        """T25 验收（消费端）：第三章任务书基础包含同型钩子差异化提醒。"""
        from data_modules.chapter_commit_service import ChapterCommitService
        from data_modules.config import DataModulesConfig
        from data_modules.index_manager import IndexManager
        from data_modules.memory_contract_adapter import MemoryContractAdapter

        manager = IndexManager(DataModulesConfig.from_project_root(root))
        manager.save_chapter_reading_power(
            __import__("data_modules.index_manager", fromlist=["ChapterReadingPowerMeta"]).ChapterReadingPowerMeta(
                chapter=1, hook_type="危机钩", hook_strength="strong"
            )
        )
        manager.save_chapter_reading_power(
            __import__("data_modules.index_manager", fromlist=["ChapterReadingPowerMeta"]).ChapterReadingPowerMeta(
                chapter=2, hook_type="危机钩", hook_strength="strong"
            )
        )

        pack = MemoryContractAdapter(DataModulesConfig.from_project_root(root)).load_context(3)

        signal = pack.sections.get("reader_signal")
        assert signal, "reader_signal section 进入基础包"
        assert "差异化" in signal["differentiation_reminder"]

    def test_reader_signal_degrades_without_index_db(self, tmp_path: Path):
        from data_modules.reader_signal_builder import build_reader_signal

        signal = build_reader_signal(tmp_path)

        assert signal == {
            "recent_reading_power": [],
            "hook_type_usage": {},
            "review_trend": [],
            "differentiation_reminder": "",
        }
