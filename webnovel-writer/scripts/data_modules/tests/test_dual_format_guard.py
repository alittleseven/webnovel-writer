#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dual_format_guard 测试：v6/v7 双格式期间的唯一写入路径（S18/E4）。

落定判定：
- v6 = `.story-system/commits/chapter_NNN.commit.json` 且 meta.status == "accepted"
- v7 = `<story_repo_root>/定稿/正文/NNNN-标题.md`（spec 0.4 §4.1，仅由 settle 写出）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from data_modules.config import DataModulesConfig  # noqa: E402
from data_modules.dual_format_guard import (  # noqa: E402
    check_unique_write_path,
    detect_chapter_formats,
    has_v6_accepted_chapter,
    has_v7_settled_chapter,
)
from data_modules.write_gates import run_write_gate  # noqa: E402
from .test_project_phase import _make_contracts, _make_init_ready  # noqa: E402


def _v6_project(tmp_path: Path, chapter: int, status: str = "accepted") -> Path:
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=chapter)
    commit_path = tmp_path / ".story-system" / "commits" / f"chapter_{chapter:03d}.commit.json"
    commit_path.parent.mkdir(parents=True, exist_ok=True)
    commit_path.write_text(
        json.dumps({"meta": {"chapter": chapter, "status": status}}, ensure_ascii=False),
        encoding="utf-8",
    )
    return tmp_path


def _v7_repo(tmp_path: Path, chapters: list[int]) -> Path:
    repo = tmp_path / "story-repo"
    for ch in chapters:
        final_dir = repo / "定稿" / "正文"
        final_dir.mkdir(parents=True, exist_ok=True)
        (final_dir / f"{ch:04d}-标题.md").write_text("正文", encoding="utf-8")
    return repo


class TestDetect:
    def test_v6_accepted_only(self, tmp_path):
        project = _v6_project(tmp_path, chapter=35, status="accepted")
        assert has_v6_accepted_chapter(project, 35) is True
        assert has_v6_accepted_chapter(project, 36) is False

    def test_v6_rejected_does_not_count(self, tmp_path):
        project = _v6_project(tmp_path, chapter=35, status="rejected")
        assert has_v6_accepted_chapter(project, 35) is False

    def test_v7_settled_by_finalized_file(self, tmp_path):
        repo = _v7_repo(tmp_path, [35])

        assert has_v7_settled_chapter(repo, 35) is True
        assert has_v7_settled_chapter(repo, 36) is False

    def test_v7_empty_repo_root_is_false(self, tmp_path):
        repo = tmp_path / "empty"
        repo.mkdir()

        assert has_v7_settled_chapter(repo, 35) is False

    def test_detect_both_formats(self, tmp_path):
        project = _v6_project(tmp_path, chapter=35)
        repo = _v7_repo(tmp_path, [36])

        formats = detect_chapter_formats(project, 35, story_repo_root=repo)

        assert formats == {"v6": True, "v7": False, "story_repo_root": str(repo)}


class TestUniqueWritePath:
    def test_v6_write_blocked_when_v7_settled(self, tmp_path):
        project = _v6_project(tmp_path, chapter=36, status="rejected")  # v6 侧该章未落定
        repo = _v7_repo(tmp_path, [36])

        issue = check_unique_write_path(project, 36, target_format="v6", story_repo_root=repo)

        assert issue is not None
        assert issue["code"] == "dual_format_write_blocked"
        assert "36" in issue["message"] and "v7" in issue["message"]

    def test_v7_write_blocked_when_v6_accepted(self, tmp_path):
        project = _v6_project(tmp_path, chapter=35, status="accepted")
        repo = _v7_repo(tmp_path, [])  # v7 侧该章未落定

        issue = check_unique_write_path(project, 35, target_format="v7", story_repo_root=repo)

        assert issue is not None
        assert issue["code"] == "dual_format_write_blocked"

    def test_no_block_when_neither_settled(self, tmp_path):
        project = _v6_project(tmp_path, chapter=36, status="rejected")
        repo = _v7_repo(tmp_path, [])

        assert check_unique_write_path(project, 36, target_format="v6", story_repo_root=repo) is None
        assert check_unique_write_path(project, 36, target_format="v7", story_repo_root=repo) is None

    def test_v6_target_without_repo_root_passes(self, tmp_path):
        project = _v6_project(tmp_path, chapter=35, status="accepted")

        assert check_unique_write_path(project, 35, target_format="v6", story_repo_root=None) is None


class TestPrewriteGateIntegration:
    def test_prewrite_blocks_when_v7_already_settled(self, tmp_path, monkeypatch):
        _make_init_ready(tmp_path)
        _make_contracts(tmp_path, chapter=1)
        repo = _v7_repo(tmp_path.parent, [1])
        # 预置环境变量（monkeypatch 自动还原，防跨测试污染）；真实使用走项目 .env
        monkeypatch.setenv("STORY_REPO_ROOT", str(repo))

        report = run_write_gate(tmp_path, chapter=1, stage="prewrite")

        assert report["ok"] is False
        assert any(item["code"] == "dual_format_write_blocked" for item in report["errors"])

    def test_prewrite_passes_without_v7(self, tmp_path, monkeypatch):
        _make_init_ready(tmp_path)
        _make_contracts(tmp_path, chapter=1)
        monkeypatch.delenv("STORY_REPO_ROOT", raising=False)

        report = run_write_gate(tmp_path, chapter=1, stage="prewrite")

        assert report["ok"] is True
