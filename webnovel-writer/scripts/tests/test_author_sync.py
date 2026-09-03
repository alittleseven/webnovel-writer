#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T3（M0）author-sync 脚本分类测试。

对应方案：docs/zcode/webnovel-copilot-300/07-feature-flows.md F-01。
契约：git diff → 六域分类（0 token 路径）→ journal 追加 + stale 标记；
内容指纹去重（同状态重跑零新事件）；>100 文件触发 migration 守卫；
系统域（.webnovel/.story-system/工作区/.cache）不产生作者事件。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def git_book(tmp_path: Path) -> Path:
    from data_modules.domain_contract import init_domain_skeleton

    root = tmp_path / "my-novel"
    root.mkdir()
    (root / "book.yaml").write_text('spec_version: "7.2"\n书名: 测试书\n', encoding="utf-8")
    init_domain_skeleton(root)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "tester")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init baseline")
    return root


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"
    return proc.stdout


def _write(root: Path, rel: str, content: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


class TestClassification:
    def test_edit_chapter_outline_creates_event_and_stale(self, git_book: Path):
        _write(git_book, "大纲/章纲/0039.md", "---\n章号: 39\n---\n改过的章纲\n")
        from data_modules.author_sync import run_author_sync

        report = run_author_sync(git_book)

        assert report["new_events"] == 1
        from data_modules.author_journal import read_journal, read_stale

        events = read_journal(git_book)
        assert events[-1]["domain"] == "章纲"
        assert events[-1]["action"] == "edit"
        assert events[-1]["diff_stat"]["ins"] > 0
        stale = read_stale(git_book)
        assert any(s["target"] == "chapter:0039" for s in stale)

    def test_domain_routing_table(self, git_book: Path):
        from data_modules.author_sync import classify_path

        cases = {
            "大纲/总纲.md": "总纲",
            "大纲/regen/总纲/v2.md": "总纲",
            "大纲/卷纲/第02卷.md": "卷纲",
            "大纲/卷纲/第02卷-时间线.md": "卷纲",
            "大纲/章纲/0040.md": "章纲",
            "大纲/条目/伏笔/F-001-xxx.md": "条目",
            "素材/活/桥段.csv": "素材",
            "素材/定版/v01/桥段.csv": "素材",
            "设定/世界观.md": "设定",
            "设定/力量锚点.yaml": "战力",
            "定稿/正文/0039-标题.md": "正文",
            "文风/宪法.md": "文风",
            "作者/author_model.md": "其他",
            "随便.txt": "其他",
        }
        for path, domain in cases.items():
            assert classify_path(path) == domain, path

    def test_change_kind_from_name_status(self, git_book: Path):
        from data_modules.author_sync import change_kind_for

        assert change_kind_for("A") == "add"
        assert change_kind_for("D") == "delete"
        assert change_kind_for("R100") == "structure"
        assert change_kind_for("M") == "content"

    def test_system_paths_ignored(self, git_book: Path):
        # .webnovel/tmp、工作区/ 已被书仓 .gitignore 挡在 git status 之外（第一重防护）；
        # 这里选会出现在 status、但必须被治理层过滤的系统域路径（第二重防护）。
        _write(git_book, ".story-system/contract.json", "{}")
        _write(git_book, ".webnovel/state.json", "{}")
        from data_modules.author_sync import run_author_sync

        report = run_author_sync(git_book)

        assert report["new_events"] == 0
        assert report["ignored"] >= 2


class TestDedup:
    def test_rerun_same_state_adds_nothing(self, git_book: Path):
        _write(git_book, "素材/活/桥段.csv", "id,名称\nTR-1,测试\n")
        from data_modules.author_sync import run_author_sync

        first = run_author_sync(git_book)
        second = run_author_sync(git_book)

        assert first["new_events"] == 1
        assert second["new_events"] == 0, "同状态重跑不应重复留账（内容指纹去重）"

    def test_incremental_after_new_edit(self, git_book: Path):
        _write(git_book, "素材/活/桥段.csv", "v1\n")
        from data_modules.author_sync import run_author_sync

        run_author_sync(git_book)
        _write(git_book, "素材/活/桥段.csv", "v2\n")
        report = run_author_sync(git_book)

        assert report["new_events"] == 1

    def test_committed_changes_not_resynced(self, git_book: Path):
        # 留账后作者 commit：diff 消失，重跑零事件且水位正常推进
        _write(git_book, "文风/宪法.md", "第一条\n")
        from data_modules.author_sync import run_author_sync

        run_author_sync(git_book)
        _git(git_book, "add", "-A")
        _git(git_book, "commit", "-qm", "author edit")
        report = run_author_sync(git_book)

        assert report["new_events"] == 0


class TestMigrationGuard:
    def test_bulk_change_requires_confirmation(self, git_book: Path):
        for i in range(120):
            _write(git_book, f"迁移批/{i:03}.md", f"内容 {i}\n")

        from data_modules.author_sync import run_author_sync

        report = run_author_sync(git_book)

        assert report["new_events"] == 0
        assert report["migration_guard"] is True
        assert report["pending_files"] == 120

    def test_confirm_migration_records_summary_event(self, git_book: Path):
        for i in range(120):
            _write(git_book, f"迁移批/{i:03}.md", f"内容 {i}\n")

        from data_modules.author_sync import run_author_sync

        report = run_author_sync(git_book, confirm_migration=True)

        assert report["new_events"] == 1
        from data_modules.author_journal import read_journal

        events = read_journal(git_book)
        assert events[-1]["change_kind"] == "structure"
        assert events[-1]["diff_stat"]["files"] == 120


class TestNonGit:
    def test_requires_git_repo(self, tmp_path: Path):
        from data_modules.author_sync import run_author_sync

        report = run_author_sync(tmp_path)
        assert report["ok"] is False
        assert "git" in report["error"]


class TestImpactSummary:
    def _report(self, **over):
        base = {
            "ok": True,
            "new_events": 2,
            "stale_marks": [
                {"target": "chapter:0039", "reason": "章纲被作者修改", "impact": []},
                {"target": "material:素材/定版/v01/桥段.csv", "reason": "定版素材被修改", "impact": []},
            ],
            "migration_guard": False,
        }
        base.update(over)
        return base

    def test_summary_lists_targets_in_author_language(self):
        from data_modules.author_sync import format_impact_summary

        text = format_impact_summary(self._report())
        assert "作者已改 2 处" in text
        assert "章纲被作者修改：chapter:0039" in text
        assert "定版素材被修改" in text

    def test_empty_when_no_new_events(self):
        from data_modules.author_sync import format_impact_summary

        assert format_impact_summary(self._report(new_events=0)) == ""
        assert format_impact_summary({"ok": False, "new_events": 0}) == ""

    def test_text_report_silent_on_zero_events(self):
        from data_modules.author_sync import format_sync_report

        assert format_sync_report(self._report(new_events=0)) == ""

    def test_text_report_contains_stale_lines(self):
        from data_modules.author_sync import format_sync_report

        text = format_sync_report(self._report())
        assert "+2 events" in text
        assert "chapter:0039" in text
