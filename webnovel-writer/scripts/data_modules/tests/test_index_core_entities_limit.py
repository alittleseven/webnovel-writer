#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""get-core-entities 的 limit 参数测试（B8：防长篇全量加载）。"""
from __future__ import annotations

from data_modules.config import DataModulesConfig
from data_modules.index_manager import EntityMeta, IndexManager


def _cfg(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return cfg


def _seed_core_entities(manager: IndexManager, count: int) -> None:
    for i in range(count):
        manager.upsert_entity(
            EntityMeta(
                id=f"ent_{i}",
                type="角色",
                canonical_name=f"实体{i}",
                tier="核心",
                first_appearance=1,
                last_appearance=1 + i,
            )
        )


def test_get_core_entities_limit_caps_result(tmp_path):
    manager = IndexManager(_cfg(tmp_path))
    _seed_core_entities(manager, 7)

    assert len(manager.get_core_entities()) == 7
    capped = manager.get_core_entities(limit=3)
    assert len(capped) == 3


def test_get_core_entities_limit_zero_or_none_means_all(tmp_path):
    manager = IndexManager(_cfg(tmp_path))
    _seed_core_entities(manager, 4)

    assert len(manager.get_core_entities(limit=0)) == 4
    assert len(manager.get_core_entities(limit=None)) == 4
