#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""output_guard 测试：CLI 大输出外置化（S10/D3）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from data_modules.output_guard import (  # noqa: E402
    OUTPUT_EXTERNALIZE_CHARS,
    externalize_if_needed,
)


def _project(tmp_path: Path) -> Path:
    (tmp_path / ".webnovel" / "tmp").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    return tmp_path


class TestExternalizeIfNeeded:
    def test_small_output_verbatim_no_file(self, tmp_path):
        project = _project(tmp_path)

        out = externalize_if_needed("短输出", tool="where", project_root=project)

        assert out == "短输出"
        assert not (project / ".webnovel" / "tmp" / "cli_out").exists()

    def test_big_output_externalized_with_stub_and_file(self, tmp_path):
        project = _project(tmp_path)
        big = json.dumps({"rows": ["数" * 50 for _ in range(600)]}, ensure_ascii=False)
        assert len(big) > OUTPUT_EXTERNALIZE_CHARS

        out = externalize_if_needed(big, tool="placeholder-scan", project_root=project)

        assert out.startswith("EXTERNALIZED")
        assert 'tool="placeholder-scan"' in out
        assert f"chars={len(big)}" in out
        dumped = project / ".webnovel" / "tmp" / "cli_out" / "placeholder-scan.txt"
        assert dumped.exists()
        assert dumped.read_text(encoding="utf-8") == big
        assert f"full-output: {dumped}" in out
        assert big[:100] in out  # head 预览保留

    def test_env_disable_restores_verbatim(self, tmp_path, monkeypatch):
        project = _project(tmp_path)
        big = "数" * 21000
        monkeypatch.setenv("WEBNOVEL_OUTPUT_EXTERNALIZE", "0")

        out = externalize_if_needed(big, tool="doctor", project_root=project)

        assert out == big
        assert not (project / ".webnovel" / "tmp" / "cli_out" / "doctor.txt").exists()

    def test_no_project_root_verbatim(self, tmp_path):
        big = "数" * 21000

        out = externalize_if_needed(big, tool="where", project_root=None)

        assert out == big

    def test_threshold_env_override(self, tmp_path, monkeypatch):
        project = _project(tmp_path)
        monkeypatch.setenv("WEBNOVEL_OUTPUT_EXTERNALIZE_CHARS", "100")
        monkeypatch.delenv("WEBNOVEL_OUTPUT_EXTERNALIZE", raising=False)

        out = externalize_if_needed("x" * 150, tool="doctor", project_root=project)

        assert out.startswith("EXTERNALIZED")


def test_integration_placeholder_scan_externalized(tmp_path):
    """进程内转发的 placeholder-scan：>20k 的 JSON 输出被外置化。"""
    import subprocess

    project = _project(tmp_path)
    (project / "设定集").mkdir(exist_ok=True)
    big = "\n".join(f"- [待补齐：条目{i}]" for i in range(600))
    (project / "设定集" / "世界观.md").write_text(big, encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable, "-X", "utf8",
            str(Path(_scripts_dir) / "webnovel.py"),
            "--project-root", str(project),
            "placeholder-scan", "--format", "json",
        ],
        capture_output=True, text=True, encoding="utf-8",
    )

    assert "EXTERNALIZED" in proc.stdout
    assert 'tool="placeholder-scan"' in proc.stdout
    dumped = project / ".webnovel" / "tmp" / "cli_out" / "placeholder-scan.txt"
    assert dumped.exists()
    assert "待补齐" in dumped.read_text(encoding="utf-8")
