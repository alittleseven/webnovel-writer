#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VectorProjectionWriter 单元测试。"""
import pytest

from data_modules.vector_projection_writer import VectorProjectionWriter


def test_event_to_text_formats_power_breakthrough():
    writer = VectorProjectionWriter.__new__(VectorProjectionWriter)
    event = {
        "event_type": "power_breakthrough",
        "chapter": 47,
        "subject": "韩立",
        "payload": {"field": "realm", "new": "筑基初期"},
    }
    text = writer._event_to_text(event)
    assert "第47章" in text
    assert "韩立" in text
    assert "筑基初期" in text


def test_delta_to_text_formats_relationship():
    writer = VectorProjectionWriter.__new__(VectorProjectionWriter)
    delta = {
        "from_entity": "韩立",
        "to_entity": "陈巧倩",
        "relationship_type": "合作",
        "chapter": 47,
    }
    text = writer._delta_to_text(delta)
    assert "第47章" in text
    assert "韩立" in text
    assert "陈巧倩" in text
    assert "合作" in text


def test_collect_chunks_from_commit():
    writer = VectorProjectionWriter.__new__(VectorProjectionWriter)
    payload = {
        "meta": {"chapter": 47, "status": "accepted"},
        "accepted_events": [
            {
                "event_type": "power_breakthrough",
                "chapter": 47,
                "subject": "韩立",
                "payload": {"field": "realm", "new": "筑基初期"},
            },
        ],
        "entity_deltas": [
            {
                "from_entity": "韩立",
                "to_entity": "陈巧倩",
                "relationship_type": "合作",
                "chapter": 47,
            },
        ],
    }
    chunks = writer._collect_chunks(payload)
    assert len(chunks) == 2
    assert chunks[0]["chunk_type"] == "event"
    assert chunks[1]["chunk_type"] == "entity_delta"
    assert chunks[0]["chunk_id"] != chunks[1]["chunk_id"]


def test_collect_chunks_assigns_unique_ids_for_same_chapter_events():
    writer = VectorProjectionWriter.__new__(VectorProjectionWriter)
    payload = {
        "meta": {"chapter": 47, "status": "accepted"},
        "accepted_events": [
            {
                "event_type": "character_state_changed",
                "chapter": 47,
                "subject": "韩立",
                "payload": {"field": "状态", "new": "警觉"},
            },
            {
                "event_type": "character_state_changed",
                "chapter": 47,
                "subject": "陈巧倩",
                "payload": {"field": "状态", "new": "迟疑"},
            },
        ],
        "entity_deltas": [],
    }

    chunks = writer._collect_chunks(payload)

    assert len(chunks) == 2
    assert len({chunk["chunk_id"] for chunk in chunks}) == 2
    assert all(chunk["scene_index"] == 0 for chunk in chunks)


def test_collect_chunks_keeps_event_id_stable_when_order_changes():
    writer = VectorProjectionWriter.__new__(VectorProjectionWriter)
    event_a = {
        "event_id": "evt-a",
        "event_type": "character_state_changed",
        "chapter": 47,
        "subject": "韩立",
        "payload": {"field": "状态", "new": "警觉"},
    }
    event_b = {
        "event_id": "evt-b",
        "event_type": "character_state_changed",
        "chapter": 47,
        "subject": "陈巧倩",
        "payload": {"field": "状态", "new": "迟疑"},
    }

    first = writer._collect_chunks(
        {"meta": {"chapter": 47}, "accepted_events": [event_a, event_b], "entity_deltas": []}
    )
    second = writer._collect_chunks(
        {"meta": {"chapter": 47}, "accepted_events": [event_b, event_a], "entity_deltas": []}
    )

    first_ids = {chunk["content"]: chunk["chunk_id"] for chunk in first}
    second_ids = {chunk["content"]: chunk["chunk_id"] for chunk in second}
    assert first_ids == second_ids


def test_rejected_commit_returns_not_applied():
    writer = VectorProjectionWriter.__new__(VectorProjectionWriter)
    writer.project_root = None
    result = writer.apply({"meta": {"status": "rejected", "chapter": 1}})
    assert result["applied"] is False


def test_store_zero_for_required_chunks_is_error(monkeypatch, tmp_path):
    writer = VectorProjectionWriter(tmp_path)
    monkeypatch.setattr(writer, "_store_chunks", lambda chunks: 0)

    result = writer.apply(
        {
            "meta": {"status": "accepted", "chapter": 47},
            "summary_text": "韩立在坊市发现丹方线索。",
            "accepted_events": [],
            "entity_deltas": [],
        }
    )

    assert result["applied"] is False
    assert result["reason"] == "error:store_failed"


def test_collect_chunks_includes_summary_and_scenes():
    writer = VectorProjectionWriter.__new__(VectorProjectionWriter)
    payload = {
        "meta": {"chapter": 47, "status": "accepted"},
        "summary_text": "韩立在坊市发现丹方线索。",
        "scenes": [
            {"index": 1, "summary": "韩立入坊市观察摊位", "location": "坊市"},
            {"scene_index": 2, "content": "陈巧倩暗中提醒韩立有人跟踪。"},
        ],
        "accepted_events": [],
        "entity_deltas": [],
    }

    chunks = writer._collect_chunks(payload)
    by_type = {}
    for chunk in chunks:
        by_type.setdefault(chunk["chunk_type"], []).append(chunk)

    assert by_type["summary"][0]["chunk_id"] == "ch0047_summary"
    assert by_type["summary"][0]["parent_chunk_id"] is None
    assert by_type["scene"][0]["parent_chunk_id"] == "ch0047_summary"
    assert by_type["scene"][0]["content"].startswith("坊市：")
    assert any(chunk["scene_index"] == 2 for chunk in by_type["scene"])


@pytest.mark.asyncio
async def test_run_store_coro_works_inside_active_event_loop():
    writer = VectorProjectionWriter.__new__(VectorProjectionWriter)

    async def store():
        return 3

    assert writer._run_store_coro(store()) == 3


def test_partial_embedding_marks_partial(monkeypatch, tmp_path):
    """P1-9：stored>0 但 <total 时应标记 partial，而非静默 applied。"""
    writer = VectorProjectionWriter(tmp_path)
    # 3 个 chunk，只有 2 个成功 embedding
    monkeypatch.setattr(writer, "_store_chunks", lambda chunks: 2)

    result = writer.apply(
        {
            "meta": {"status": "accepted", "chapter": 47},
            "summary_text": "摘要",
            "accepted_events": [
                {"event_type": "power_breakthrough", "chapter": 47, "subject": "a", "payload": {"new": "筑基"}},
                {"event_type": "character_state_changed", "chapter": 47, "subject": "b", "payload": {"field": "x", "new": "y"}},
            ],
            "entity_deltas": [],
        }
    )

    assert result["applied"] is True
    assert result["partial"] is True
    assert result["reason"] == "embedding_partial"
    assert result["stored"] == 2
    assert result["total"] == 3


def test_full_embedding_not_partial(monkeypatch, tmp_path):
    writer = VectorProjectionWriter(tmp_path)
    monkeypatch.setattr(writer, "_store_chunks", lambda chunks: 1)

    result = writer.apply(
        {
            "meta": {"status": "accepted", "chapter": 47},
            "summary_text": "摘要",
            "accepted_events": [],
            "entity_deltas": [],
        }
    )

    assert result["applied"] is True
    assert "partial" not in result
    assert result["total"] == 1
