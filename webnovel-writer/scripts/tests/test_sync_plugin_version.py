#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_plugin_version 需把 mcp/server.py 的 SERVER_VERSION 纳入同步与校验（复审报告 P1-7）。"""

import json
import sys
from pathlib import Path

import pytest


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[1]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_ensure_scripts_on_path()

import sync_plugin_version as spv  # noqa: E402


README_TEMPLATE = """# Webnovel Writer

[![Version](https://img.shields.io/badge/version-{version}-brightgreen.svg)](marketplace.json)

| 版本 | 说明 |
|------|------|
| **v{version} (当前)** | 说明 |
"""


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def release_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    plugin_json = tmp_path / "webnovel-writer" / ".zcode-plugin" / "plugin.json"
    marketplace = tmp_path / "marketplace.json"
    mirror = tmp_path / ".claude-plugin" / "marketplace.json"
    readme = tmp_path / "README.md"
    server = tmp_path / "webnovel-writer" / "mcp" / "server.py"

    _write_json(plugin_json, {"name": "webnovel-writer", "version": "8.0.0"})
    payload = {"plugins": [{"name": "webnovel-writer", "version": "8.0.0"}]}
    _write_json(marketplace, payload)
    _write_json(mirror, payload)
    readme.write_text(README_TEMPLATE.format(version="8.0.0"), encoding="utf-8")
    server.parent.mkdir(parents=True, exist_ok=True)
    server.write_text(
        'SERVER_NAME = "webnovel"\nSERVER_VERSION = "7.1.0"\n', encoding="utf-8"
    )

    monkeypatch.setattr(spv, "PLUGIN_JSON_CANDIDATES", (plugin_json,))
    monkeypatch.setattr(spv, "MARKETPLACE_JSON_PATHS", (marketplace, mirror))
    monkeypatch.setattr(spv, "README_PATH", readme)
    monkeypatch.setattr(spv, "MCP_SERVER_PATH", server)
    return tmp_path


def test_check_reports_server_version_mismatch(release_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert spv.check_versions() == 1
    out = capsys.readouterr().out
    assert "mcp/server.py SERVER_VERSION=7.1.0" in out


def test_sync_rewrites_server_version(release_root: Path) -> None:
    previous, target, changed = spv.sync_versions()

    assert (previous, target, changed) == ("8.0.0", "8.0.0", True)
    server_text = (release_root / "webnovel-writer" / "mcp" / "server.py").read_text(encoding="utf-8")
    assert 'SERVER_VERSION = "8.0.0"' in server_text
    assert 'SERVER_NAME = "webnovel"' in server_text
    assert spv.check_versions() == 0


def test_repo_server_version_matches_plugin_manifest() -> None:
    """真仓守卫：server.py 的 SERVER_VERSION 必须与 plugin.json 一致。"""
    plugin_version = spv.load_json(spv.find_plugin_json())["version"]
    assert spv.get_server_version(spv.load_text(spv.MCP_SERVER_PATH)) == plugin_version
