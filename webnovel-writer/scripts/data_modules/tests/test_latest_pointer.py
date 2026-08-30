#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""latest.json 指针测试（S7/P2-1）：防逐章回扫，含跳章 / 指针失效 / 回头补写场景。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from data_modules.story_contracts import StoryContractPaths  # noqa: E402
from data_modules.story_runtime_sources import (  # noqa: E402
    _load_latest_accepted_commit,
    _load_latest_commit,
    load_runtime_sources,
)


def _commit(chapter: int, status: str = "accepted") -> dict:
    return {
        "meta": {"schema_version": "story-system/v1", "chapter": chapter, "status": status},
        "marker": f"COMMIT-{chapter}",
    }


def _project(tmp_path: Path, commits: list[int], accepted: set[int] | None = None) -> tuple[Path, StoryContractPaths]:
    accepted = accepted if accepted is not None else set(commits)
    paths = StoryContractPaths.from_project_root(tmp_path)
    paths.commits_dir.mkdir(parents=True, exist_ok=True)
    for ch in commits:
        paths.commit_json(ch).write_text(
            json.dumps(_commit(ch, "accepted" if ch in accepted else "rejected"), ensure_ascii=False),
            encoding="utf-8",
        )
    return tmp_path, paths


def _write_pointer(tmp_path: Path, latest: int | None, accepted: int | None) -> None:
    paths = StoryContractPaths.from_project_root(tmp_path)
    paths.commits_dir.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": "test"}
    if latest is not None:
        payload["latest_chapter"] = latest
    if accepted is not None:
        payload["latest_accepted_chapter"] = accepted
    (paths.commits_dir / "latest.json").write_text(json.dumps(payload), encoding="utf-8")


class TestLoadLatestCommitWithPointer:
    def test_pointer_hit_skips_earlier_scans(self, tmp_path, monkeypatch):
        project, paths = _project(tmp_path, [1, 2, 3])
        _write_pointer(tmp_path, latest=3, accepted=3)

        # 类级 spy：实例分派必然命中同一下类对象，不受模块双身份影响
        requested: list[int] = []
        original = StoryContractPaths.commit_json

        def spy(self, chapter: int):
            requested.append(chapter)
            return original(self, chapter)

        monkeypatch.setattr(StoryContractPaths, "commit_json", spy)

        payload = _load_latest_commit(paths, 3)

        assert payload["marker"] == "COMMIT-3"
        assert requested == [3]  # 直达指针章，未回扫 1/2

    def test_no_pointer_falls_back_to_scan(self, tmp_path):
        project, paths = _project(tmp_path, [1, 2, 3])

        payload = _load_latest_commit(paths, 3)

        assert payload["marker"] == "COMMIT-3"

    def test_skip_chapter_requests_below_pointer(self, tmp_path):
        """跳章：1、3 有 commit（2 被跳过），请求第 2 章上下文。"""
        project, paths = _project(tmp_path, [1, 3])
        _write_pointer(tmp_path, latest=3, accepted=3)

        assert _load_latest_commit(paths, 3)["marker"] == "COMMIT-3"
        assert _load_latest_commit(paths, 2)["marker"] == "COMMIT-1"  # 指针越界→回扫

    def test_stale_pointer_self_heals(self, tmp_path):
        """指针失效（文件被删）：回退线性扫描，不崩溃、结果正确。"""
        project, paths = _project(tmp_path, [1, 2, 3])
        _write_pointer(tmp_path, latest=5, accepted=5)

        assert _load_latest_commit(paths, 5)["marker"] == "COMMIT-3"

    def test_pointer_ignores_chapter_above_range(self, tmp_path):
        project, paths = _project(tmp_path, [1, 2])
        _write_pointer(tmp_path, latest=2, accepted=2)

        # 请求第 5 章：指针 2 在范围内仍可直达
        assert _load_latest_commit(paths, 5)["marker"] == "COMMIT-2"


class TestLoadLatestAcceptedWithPointer:
    def test_accepted_pointer_skips_rejected_tail(self, tmp_path):
        """2 rejected、3 accepted：accepted 指针直达 3，latest 同为 3。"""
        project, paths = _project(tmp_path, [1, 2, 3], accepted={1, 3})
        _write_pointer(tmp_path, latest=3, accepted=3)

        assert _load_latest_commit(paths, 3)["marker"] == "COMMIT-3"
        assert _load_latest_accepted_commit(paths, 3)["marker"] == "COMMIT-3"

    def test_accepted_pointer_trailing_rejected(self, tmp_path):
        """跳章+尾部 rejected：1 accepted、2 rejected、3 rejected，请求 3。"""
        project, paths = _project(tmp_path, [1, 2, 3], accepted={1})
        _write_pointer(tmp_path, latest=3, accepted=1)

        assert _load_latest_commit(paths, 3)["marker"] == "COMMIT-3"
        assert _load_latest_accepted_commit(paths, 3)["marker"] == "COMMIT-1"


class TestPersistUpdatesPointer:
    def test_persist_commit_writes_pointer(self, tmp_path):
        from data_modules.chapter_commit_service import ChapterCommitService

        service = ChapterCommitService(tmp_path)
        service.persist_commit(_commit(2))
        service.persist_commit(_commit(3, status="rejected"))

        pointer = json.loads(
            (tmp_path / ".story-system" / "commits" / "latest.json").read_text(encoding="utf-8")
        )
        assert pointer["latest_chapter"] == 3  # max 语义
        assert pointer["latest_accepted_chapter"] == 2  # rejected 不推进 accepted

    def test_persist_backfill_does_not_regress_pointer(self, tmp_path):
        """回头补写：3 已存在指针，补写 1 不得使指针回退。"""
        from data_modules.chapter_commit_service import ChapterCommitService

        service = ChapterCommitService(tmp_path)
        service.persist_commit(_commit(3))

        service_back = ChapterCommitService(tmp_path)
        service_back.persist_commit(_commit(1))

        pointer = json.loads(
            (tmp_path / ".story-system" / "commits" / "latest.json").read_text(encoding="utf-8")
        )
        assert pointer["latest_chapter"] == 3


class TestRuntimeSourcesIntegration:
    def test_load_runtime_sources_with_pointer_no_fallback(self, tmp_path):
        _project(tmp_path, [1, 2, 3])
        _write_pointer(tmp_path, latest=3, accepted=3)

        snapshot = load_runtime_sources(tmp_path, 4)

        assert snapshot.latest_commit["marker"] == "COMMIT-3"
        assert snapshot.latest_accepted_commit["marker"] == "COMMIT-3"
        assert snapshot.fallback_sources == ["missing_master_contract"] or all(
            "accepted_commit" not in item for item in snapshot.fallback_sources
        )
