#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def test_dashboard_watcher_notifies_story_system_commit_changes(tmp_path):
    from dashboard.watcher import _WebnovelFileHandler

    changed = []
    handler = _WebnovelFileHandler(
        lambda path, kind: changed.append((Path(path).name, kind)),
        watch_webnovel_dir=tmp_path / ".webnovel",
        watch_story_system_dir=tmp_path / ".story-system",
    )

    event = SimpleNamespace(
        is_directory=False,
        src_path=str(tmp_path / ".story-system" / "commits" / "chapter_003.commit.json"),
    )

    handler.on_modified(event)

    assert changed == [("chapter_003.commit.json", "modified")]


def test_dashboard_watcher_notifies_index_db_wal_writes(tmp_path):
    """增量审阅 P3-18：WAL 模式下实体写入先进 index.db-wal，主文件 mtime 不变——必须盯 wal/shm。"""
    from dashboard.watcher import _WebnovelFileHandler

    changed = []
    handler = _WebnovelFileHandler(
        lambda path, kind: changed.append((Path(path).name, kind)),
        watch_webnovel_dir=tmp_path / ".webnovel",
        watch_story_system_dir=tmp_path / ".story-system",
    )

    for name in ("index.db-wal", "index.db-shm"):
        event = SimpleNamespace(
            is_directory=False,
            src_path=str(tmp_path / ".webnovel" / name),
        )
        handler.on_modified(event)

    assert changed == [("index.db-wal", "modified"), ("index.db-shm", "modified")]
