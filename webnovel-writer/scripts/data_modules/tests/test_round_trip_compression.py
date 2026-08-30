#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S9/D2 往返压缩测试：preflight --all 三查合一 + run-ledger 批量记账。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from data_modules.config import DataModulesConfig  # noqa: E402


def _project(tmp_path: Path, with_placeholder: bool = False) -> Path:
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    settings = tmp_path / "设定集"
    settings.mkdir(exist_ok=True)
    body = "世界观核心\n- [待补齐：大陆名称]\n" if with_placeholder else "世界观核心\n"
    (settings / "世界观.md").write_text(body, encoding="utf-8")
    return tmp_path


class TestPreflightAll:
    def _run(self, project: Path, capsys):
        from data_modules.webnovel import cmd_preflight

        ns = argparse.Namespace(project_root=str(project), format="text", all_flag=True)
        rc = cmd_preflight(ns)
        return rc, capsys.readouterr().out

    def test_all_prints_root_placeholders_and_checks(self, tmp_path, capsys):
        project = _project(tmp_path)

        rc, out = self._run(project, capsys)

        assert rc == 0
        assert "PROJECT_ROOT=" in out
        assert str(project) in out
        assert "placeholder" in out.lower()
        assert "scripts_dir" in out  # 原 preflight 检查项保留

    def test_all_flags_placeholders_and_fails(self, tmp_path, capsys):
        project = _project(tmp_path, with_placeholder=True)

        rc, out = self._run(project, capsys)

        assert rc == 1  # 占位符存在 → 非零退出
        assert "PLACEHOLDER count=1" in out
        assert "设定集/世界观.md:2" in out

    def test_without_all_flag_unchanged(self, tmp_path, capsys):
        from data_modules.webnovel import cmd_preflight

        project = _project(tmp_path)
        ns = argparse.Namespace(project_root=str(project), format="text", all_flag=False)

        rc = cmd_preflight(ns)
        out = capsys.readouterr().out

        assert rc == 0
        assert "PROJECT_ROOT=" not in out  # 旧行为不受影响


class TestRecordWriteStepsBatch:
    def test_batch_records_multiple_steps(self, tmp_path):
        from data_modules.run_ledger import load_ledger
        from data_modules.webnovel import cmd_run_ledger

        project = _project(tmp_path)
        steps = [
            {"step": "draft", "status": "completed", "duration_ms": 100},
            {"step": "review", "status": "completed", "problems": ["略慢"]},
            {"step": "data", "status": "completed"},
        ]
        ns = argparse.Namespace(
            project_root=str(project),
            ledger_action="record-write-steps",
            chapter=36,
            mode="standard",
            steps_json=json.dumps(steps),
        )

        rc = cmd_run_ledger(ns)

        assert rc == 0
        ledger = load_ledger(project)
        recorded = ledger["write"]["chapter_036"]["steps"]
        assert set(recorded) >= {"draft", "review", "data"}
        assert recorded["review"]["problems"] == ["略慢"]

    def test_batch_rejects_non_list(self, tmp_path, capsys):
        from data_modules.webnovel import cmd_run_ledger

        project = _project(tmp_path)
        ns = argparse.Namespace(
            project_root=str(project),
            ledger_action="record-write-steps",
            chapter=36,
            mode="standard",
            steps_json=json.dumps({"step": "draft"}),
        )

        rc = cmd_run_ledger(ns)

        assert rc == 2
        assert "list" in capsys.readouterr().err
