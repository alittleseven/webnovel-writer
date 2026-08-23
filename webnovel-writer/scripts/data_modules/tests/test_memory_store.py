#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from data_modules.config import DataModulesConfig
from data_modules.memory.schema import MemoryItem
from data_modules.memory.store import ScratchpadManager


def _cfg(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return cfg


def test_load_empty_file(tmp_path):
    manager = ScratchpadManager(_cfg(tmp_path))
    data = manager.load()
    assert data.count_items() == 0


def test_upsert_character_state_marks_old_outdated(tmp_path):
    manager = ScratchpadManager(_cfg(tmp_path))
    item1 = MemoryItem(
        id="a1",
        layer="semantic",
        category="character_state",
        subject="xiaoyan",
        field="realm",
        value="斗者",
        source_chapter=1,
    )
    item2 = MemoryItem(
        id="a2",
        layer="semantic",
        category="character_state",
        subject="xiaoyan",
        field="realm",
        value="斗师",
        source_chapter=2,
    )
    manager.upsert_item(item1)
    manager.upsert_item(item2)
    active = manager.query(category="character_state", subject="xiaoyan", status="active")
    outdated = manager.query(category="character_state", subject="xiaoyan", status="outdated")
    assert len(active) == 1
    assert active[0].value == "斗师"
    assert len(outdated) == 1


def test_upsert_world_rule_with_subject_field_key(tmp_path):
    manager = ScratchpadManager(_cfg(tmp_path))
    manager.upsert_item(
        MemoryItem(
            id="w1",
            layer="semantic",
            category="world_rule",
            subject="修炼体系",
            field="境界划分",
            value="九境",
            source_chapter=1,
        )
    )
    manager.upsert_item(
        MemoryItem(
            id="w2",
            layer="semantic",
            category="world_rule",
            subject="修炼体系",
            field="突破条件",
            value="需心境",
            source_chapter=2,
        )
    )
    rows = manager.query(category="world_rule", status="active")
    assert len(rows) == 2


def test_timeline_same_subject_different_chapter_should_append(tmp_path):
    manager = ScratchpadManager(_cfg(tmp_path))
    manager.upsert_item(
        MemoryItem(
            id="t1",
            layer="semantic",
            category="timeline",
            subject="离开宗门",
            field="event",
            value="离开宗门",
            source_chapter=10,
        )
    )
    manager.upsert_item(
        MemoryItem(
            id="t2",
            layer="semantic",
            category="timeline",
            subject="离开宗门",
            field="event",
            value="离开宗门",
            source_chapter=20,
        )
    )
    rows = manager.query(category="timeline", status="active")
    assert len(rows) == 2


def test_mark_status_and_stats(tmp_path):
    manager = ScratchpadManager(_cfg(tmp_path))
    manager.upsert_item(
        MemoryItem(
            id="p1",
            layer="semantic",
            category="reader_promise",
            subject="纳兰嫣然出场",
            field="promise",
            value="纳兰嫣然会在宗门大比前出场",
            source_chapter=8,
        )
    )
    assert manager.mark_status("p1", "tentative") is True
    rows = manager.query(category="reader_promise", status="tentative")
    assert len(rows) == 1
    stats = manager.stats()
    assert stats["total"] >= 1


def test_correct_updates_value_by_id(tmp_path):
    manager = ScratchpadManager(_cfg(tmp_path))
    manager.upsert_item(
        MemoryItem(
            id="c1",
            layer="semantic",
            category="world_rule",
            subject="修炼体系",
            field="境界划分",
            value="九境",
            source_chapter=1,
        )
    )
    result = manager.correct(item_id="c1", value="十境")
    assert result["matched"] == 1
    assert result["updated"] == 1
    rows = manager.query(category="world_rule", status="active")
    assert rows[0].value == "十境"


def test_correct_adjusts_status_by_category_subject(tmp_path):
    manager = ScratchpadManager(_cfg(tmp_path))
    manager.upsert_item(
        MemoryItem(
            id="c2",
            layer="semantic",
            category="character_state",
            subject="xiaoyan",
            field="realm",
            value="斗者",
            source_chapter=1,
        )
    )
    result = manager.correct(category="character_state", subject="xiaoyan", status="outdated")
    assert result["matched"] == 1
    assert result["updated"] == 1
    assert manager.query(category="character_state", subject="xiaoyan", status="outdated")


def test_correct_deletes_matched_items(tmp_path):
    manager = ScratchpadManager(_cfg(tmp_path))
    manager.upsert_item(
        MemoryItem(
            id="c3",
            layer="semantic",
            category="story_fact",
            subject="错误事实",
            field="描述",
            value="错误内容",
            source_chapter=1,
        )
    )
    result = manager.correct(item_id="c3", delete=True)
    assert result["deleted"] == 1
    assert manager.query(category="story_fact", status="active") == []


def test_correct_requires_locator(tmp_path):
    manager = ScratchpadManager(_cfg(tmp_path))
    result = manager.correct(value="x")
    assert result.get("error") == "missing_locator"


def test_correct_requires_change(tmp_path):
    manager = ScratchpadManager(_cfg(tmp_path))
    result = manager.correct(item_id="missing", )
    assert result.get("error") == "nothing_to_change"


def test_correct_rejects_invalid_status(tmp_path):
    manager = ScratchpadManager(_cfg(tmp_path))
    result = manager.correct(item_id="c1", status="bogus")
    assert result.get("error") == "invalid_status"


def test_correct_not_found_when_no_match(tmp_path):
    manager = ScratchpadManager(_cfg(tmp_path))
    result = manager.correct(item_id="nonexistent", value="x")
    assert result["not_found"] is True
    assert result["matched"] == 0


def test_compactor_enforces_global_limit_and_dedupes_timeline_summary(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.memory_compactor_enabled = True
    cfg.memory_compactor_threshold = 3
    manager = ScratchpadManager(cfg)

    manager.upsert_item(
        MemoryItem(
            id="t-old-1",
            layer="semantic",
            category="timeline",
            subject="事件一",
            field="event",
            value="事件一",
            source_chapter=1,
        )
    )
    manager.upsert_item(
        MemoryItem(
            id="t-old-2",
            layer="semantic",
            category="timeline",
            subject="事件二",
            field="event",
            value="事件二",
            source_chapter=2,
        )
    )
    manager.upsert_item(
        MemoryItem(
            id="t-fresh",
            layer="semantic",
            category="timeline",
            subject="事件三",
            field="event",
            value="事件三",
            source_chapter=60,
        )
    )
    manager.upsert_item(
        MemoryItem(
            id="w1",
            layer="semantic",
            category="world_rule",
            subject="修炼体系",
            field="境界划分",
            value="九境",
            source_chapter=60,
        )
    )

    dump1 = manager.dump()
    total1 = sum(len(v) for k, v in dump1.items() if isinstance(v, list))
    assert total1 <= 3
    summary_count1 = sum(
        1
        for row in dump1.get("story_facts", [])
        if row.get("subject") == "timeline_summary"
    )
    assert summary_count1 <= 1

    manager.upsert_item(
        MemoryItem(
            id="w2",
            layer="semantic",
            category="world_rule",
            subject="地理",
            field="区域",
            value="中州",
            source_chapter=61,
        )
    )
    dump2 = manager.dump()
    total2 = sum(len(v) for k, v in dump2.items() if isinstance(v, list))
    assert total2 <= 3
    summary_count2 = sum(
        1
        for row in dump2.get("story_facts", [])
        if row.get("subject") == "timeline_summary"
    )
    assert summary_count2 <= 1
