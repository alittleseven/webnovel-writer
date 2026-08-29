#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""settings_digest 测试：设定集 L0 摘要层（S3/C3）。"""
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
from data_modules.context_manager import ContextManager  # noqa: E402
from data_modules.settings_digest import (  # noqa: E402
    build_digest,
    get_setting_digest,
)

SAMPLE_MD = """# 世界观

## 天裂
天裂横在头顶，一天宽一线。

## 潮汐规则
风暴每七日一次。

## 铁门禁地
入夜不过石灰线。
"""


def _cfg(tmp_path: Path) -> DataModulesConfig:
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return cfg


def _write_setting(tmp_path: Path, name: str, text: str) -> None:
    (tmp_path / "设定集").mkdir(parents=True, exist_ok=True)
    (tmp_path / "设定集" / f"{name}.md").write_text(text, encoding="utf-8")


class TestBuildDigest:
    def test_contains_structure_and_within_limit(self):
        digest = build_digest(SAMPLE_MD, max_chars=240)

        assert digest.startswith("世界观")
        assert "天裂" in digest and "潮汐规则" in digest and "铁门禁地" in digest
        assert len(digest) <= 240

    def test_long_text_truncated_with_marker(self):
        text = "# 主题\n\n" + "长" * 600

        digest = build_digest(text, max_chars=240)

        assert len(digest) <= 240
        assert digest.endswith("…（L0 截断）")

    def test_deterministic(self):
        assert build_digest(SAMPLE_MD) == build_digest(SAMPLE_MD)


class TestGetSettingDigest:
    def test_builds_and_caches_record(self, tmp_path):
        cfg = _cfg(tmp_path)
        _write_setting(tmp_path, "世界观", SAMPLE_MD)

        digest = get_setting_digest(cfg, "世界观")

        assert "天裂" in digest
        record_path = tmp_path / ".webnovel" / "settings_digest" / "世界观.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        assert record["digest"] == digest
        assert len(record["source_sha256"]) == 64

    def test_stale_source_regenerates(self, tmp_path):
        cfg = _cfg(tmp_path)
        _write_setting(tmp_path, "世界观", SAMPLE_MD)
        first = get_setting_digest(cfg, "世界观")

        # L0 只含标题骨架：改动 ## 标题必然改变摘要；同时源 sha 变化触发重建
        changed = SAMPLE_MD.replace("## 潮汐规则", "## 潮汐规则改")
        _write_setting(tmp_path, "世界观", changed)
        second = get_setting_digest(cfg, "世界观")

        assert first != second
        assert "潮汐规则改" in second
        record = json.loads(
            (tmp_path / ".webnovel" / "settings_digest" / "世界观.json").read_text(encoding="utf-8")
        )
        assert record["source_sha256"] != __import__("hashlib").sha256(
            SAMPLE_MD.encode("utf-8")
        ).hexdigest()

    def test_missing_source_returns_empty(self, tmp_path):
        cfg = _cfg(tmp_path)

        assert get_setting_digest(cfg, "不存在") == ""

    def test_fallback_glob_matches_partial_name(self, tmp_path):
        cfg = _cfg(tmp_path)
        _write_setting(tmp_path, "力量体系-详版", SAMPLE_MD)

        assert "天裂" in get_setting_digest(cfg, "力量体系")


class TestLoadSettingIntegration:
    def test_load_setting_returns_digest_when_enabled(self, tmp_path):
        cfg = _cfg(tmp_path)
        _write_setting(tmp_path, "世界观", SAMPLE_MD + "尾" * 2000)
        manager = ContextManager(cfg)

        text = manager._load_setting("世界观")

        assert len(text) <= 240  # L0 摘要，而非 4000 字截头
        assert "天裂" in text

    def test_load_setting_disabled_falls_back_to_full(self, tmp_path):
        cfg = _cfg(tmp_path)
        cfg.context_settings_digest_enabled = False
        _write_setting(tmp_path, "世界观", SAMPLE_MD + "尾" * 2000)
        manager = ContextManager(cfg)

        text = manager._load_setting("世界观")

        assert "天裂" in text and "尾尾尾" in text  # 旧路径：全文（≤4000 截头）

    def test_load_setting_missing_reports_not_found(self, tmp_path):
        cfg = _cfg(tmp_path)
        manager = ContextManager(cfg)

        assert manager._load_setting("不存在") == "[不存在设定未找到]"


class TestSettingReadCli:
    def test_reads_full_text_with_optional_cap(self, tmp_path, capsys):
        from data_modules.webnovel import cmd_setting_read

        _cfg(tmp_path)
        (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
        _write_setting(tmp_path, "世界观", SAMPLE_MD + "尾" * 3000)

        cmd_setting_read(argparse.Namespace(project_root=str(tmp_path), name="世界观", max_chars=0))
        full = capsys.readouterr().out
        assert "天裂" in full and "尾尾尾" in full

        cmd_setting_read(argparse.Namespace(project_root=str(tmp_path), name="世界观", max_chars=100))
        capped = capsys.readouterr().out
        assert len(capped.strip()) <= 100

    def test_missing_name_reports_error(self, tmp_path, capsys):
        from data_modules.webnovel import cmd_setting_read

        _cfg(tmp_path)
        (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
        cmd_setting_read(argparse.Namespace(project_root=str(tmp_path), name="不存在", max_chars=0))
        out = capsys.readouterr().out
        assert "未找到" in out
