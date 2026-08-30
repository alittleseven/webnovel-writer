#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""graph 候选收集 SQL 下推测试（S7/P2-1）：行为与全表过滤等价，扫描下沉 SQLite。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from data_modules.config import DataModulesConfig  # noqa: E402
from data_modules.index_manager import EntityMeta  # noqa: E402
from data_modules.rag_adapter import RAGAdapter  # noqa: E402


def _entity(entity_id: str, name: str) -> EntityMeta:
    return EntityMeta(
        id=entity_id,
        type="角色",
        canonical_name=name,
        tier="核心",
        first_appearance=1,
        last_appearance=3,
    )


class _FakeClient:
    async def embed(self, texts):
        return [[0.0] * 4 for _ in texts]

    async def embed_batch(self, texts, skip_failures=True):
        return [[0.0] * 4 for _ in texts]

    async def rerank(self, query, documents, top_n=None):
        return documents[: top_n or len(documents)]


@pytest.fixture()
def adapter(tmp_path, monkeypatch):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    monkeypatch.setattr("data_modules.rag_adapter.get_client", lambda config: _FakeClient())
    adapter = RAGAdapter(cfg)
    return adapter


def _chunk(chapter: int, scene: int, content: str) -> dict:
    return {"chapter": chapter, "scene_index": scene, "content": content}


@pytest.mark.asyncio
async def test_collect_candidates_matching_entities_only(adapter):
    chunks = [
        _chunk(1, 1, "苏小白在据点议事"),
        _chunk(1, 2, "林知夏核账到深夜"),
        _chunk(2, 1, "苏小白与林知夏同行"),
        _chunk(2, 2, "与两人无关的内容"),
    ]
    await adapter.store_chunks(chunks)
    adapter.index_manager.upsert_entity(_entity("su", "苏小白"))

    ids = adapter._collect_graph_candidate_chunk_ids(["su"])

    assert len(ids) == 2  # 只命中含「苏小白」的两块
    assert all(isinstance(i, str) for i in ids)


@pytest.mark.asyncio
async def test_collect_candidates_respects_chapter_upper_bound(adapter):
    chunks = [
        _chunk(1, 1, "老周表态不交七成"),
        _chunk(3, 1, "老周再次出场"),
    ]
    await adapter.store_chunks(chunks)
    adapter.index_manager.upsert_entity(_entity("zhou", "老周"))

    ids = adapter._collect_graph_candidate_chunk_ids(["zhou"], chapter=2)

    assert len(ids) == 1  # chapter<=2 过滤掉第 3 章


@pytest.mark.asyncio
async def test_collect_candidates_no_terms_returns_empty(adapter):
    assert adapter._collect_graph_candidate_chunk_ids(["ghost"]) == []
