#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from data_modules.config import DataModulesConfig
from data_modules.memory.orchestrator import MemoryOrchestrator
from data_modules.memory.schema import MemoryItem
from data_modules.memory.store import ScratchpadManager


def _cfg(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return cfg


def test_build_memory_pack_empty(tmp_path):
    orchestrator = MemoryOrchestrator(_cfg(tmp_path))
    pack = orchestrator.build_memory_pack(1)
    assert pack["stats"]["total"] == 0
    assert pack["semantic_memory"] == []
    assert "long_term_facts" not in pack
    assert "active_constraints" not in pack
    assert "working_memory" in pack
    assert "episodic_memory" in pack
    assert "semantic_memory" in pack


def test_build_memory_pack_filter_and_budget(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.memory_orchestrator_max_items = 1
    outline_dir = cfg.project_root / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)
    (outline_dir / "第1卷 详细大纲.md").write_text("### 第10章：萧炎突破\n", encoding="utf-8")

    store = ScratchpadManager(cfg)
    store.upsert_item(
        MemoryItem(
            id="m1",
            layer="semantic",
            category="character_state",
            subject="萧炎",
            field="realm",
            value="斗师",
            source_chapter=9,
        )
    )
    store.upsert_item(
        MemoryItem(
            id="m2",
            layer="semantic",
            category="story_fact",
            subject="chapter_hook",
            field="9",
            value="神秘强者出现",
            source_chapter=9,
        )
    )

    orchestrator = MemoryOrchestrator(cfg)
    pack = orchestrator.build_memory_pack(10)
    assert pack["stats"]["total"] >= 2
    assert len(pack["semantic_memory"]) == 1
    assert pack["stats"]["semantic_total"] >= 1


def _seed_state(tmp_path, cfg, pending: int, thread_items: int) -> None:
    import json

    state = {
        "protagonist_state": {"name": "萧炎"},
        "plot_threads": {"foreshadowing": [{"id": i, "note": f"伏笔{i}"} for i in range(thread_items)]},
        "disambiguation_pending": [{"mention": f"实体{i}"} for i in range(pending)],
    }
    (cfg.project_root / ".webnovel" / "state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )


def _state_export(pack):
    working = pack["working_memory"]
    return next(item for item in working if item["source"] == "state_export")["content"]


def test_state_export_capped_to_limit(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_state(tmp_path, cfg, pending=15, thread_items=15)

    pack = MemoryOrchestrator(cfg).build_memory_pack(1)

    export = _state_export(pack)
    assert len(export["disambiguation_pending"]) == 10
    assert len(export["plot_threads"]["foreshadowing"]) == 10


def test_state_export_limit_zero_keeps_all(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.memory_state_export_pending_limit = 0
    _seed_state(tmp_path, cfg, pending=15, thread_items=3)

    pack = MemoryOrchestrator(cfg).build_memory_pack(1)

    export = _state_export(pack)
    assert len(export["disambiguation_pending"]) == 15
    assert len(export["plot_threads"]["foreshadowing"]) == 3


def test_episodic_memory_has_no_state_change_duplicate(tmp_path):
    cfg = _cfg(tmp_path)

    pack = MemoryOrchestrator(cfg).build_memory_pack(1)

    assert all(item["source"] != "state_change" for item in pack["episodic_memory"])
    assert "recent_changes" in pack
