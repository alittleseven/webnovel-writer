#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1-2：合同 schema 版本检测与迁移框架测试。"""

import json
import sys
from pathlib import Path

import pytest


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_ensure_scripts_on_path()

import data_modules.contract_migrations as cm  # noqa: E402
from data_modules.contract_migrations import (  # noqa: E402
    ContractMigrationError,
    migrate_contracts_if_needed,
)


def _write_contract(root: Path, rel: str, meta: dict) -> Path:
    path = root / ".story-system" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"meta": meta, "payload": {"x": 1}}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def test_parse_version_extracts_number():
    assert cm._parse_version("story-system/v1") == 1
    assert cm._parse_version("story-system/v12") == 12
    assert cm._parse_version("") == 0
    assert cm._parse_version("garbage") == 0


def test_no_migration_when_already_current(tmp_path):
    path = _write_contract(tmp_path, "MASTER_SETTING.json", {"schema_version": "story-system/v1"})
    report = migrate_contracts_if_needed(tmp_path)

    assert report["migrated"] == []
    assert report["unchanged"] >= 1
    assert report["errors"] == []
    # 文件内容未被改动
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["meta"]["schema_version"] == "story-system/v1"


def test_migrate_old_version_runs_registered_migration(monkeypatch, tmp_path):
    # 注册一个 v1 -> v2 的迁移，并临时把当前版本设为 v2 以触发。
    calls: list = []

    def fake_migrate_v1(payload):
        calls.append(payload)
        payload["added_field"] = "migrated"
        return payload

    monkeypatch.setattr(cm, "CONTRACT_MIGRATIONS", {1: fake_migrate_v1})
    monkeypatch.setattr(cm, "CONTRACT_SCHEMA_VERSION", "story-system/v2")
    path = _write_contract(tmp_path, "chapters/chapter_001.json", {"schema_version": "story-system/v1"})

    report = migrate_contracts_if_needed(tmp_path)

    assert len(report["migrated"]) == 1
    assert len(calls) == 1
    assert report["backed_up"], "迁移前应产生备份"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["added_field"] == "migrated"
    assert payload["meta"]["schema_version"] == "story-system/v2"


def test_migration_backs_up_before_write(monkeypatch, tmp_path):
    def fake_migrate_v1(payload):
        payload["v2"] = True
        return payload

    monkeypatch.setattr(cm, "CONTRACT_MIGRATIONS", {1: fake_migrate_v1})
    monkeypatch.setattr(cm, "CONTRACT_SCHEMA_VERSION", "story-system/v2")
    path = _write_contract(tmp_path, "volumes/volume_001.json", {"schema_version": "story-system/v1"})

    report = migrate_contracts_if_needed(tmp_path)

    assert len(report["backed_up"]) == 1
    backup_path = Path(report["backed_up"][0])
    assert backup_path.is_file()
    # 备份内容是迁移前的旧版本
    backup_payload = json.loads(backup_path.read_text(encoding="utf-8"))
    assert "v2" not in backup_payload


def test_missing_migration_function_reports_error(monkeypatch, tmp_path):
    monkeypatch.setattr(cm, "CONTRACT_MIGRATIONS", {})
    monkeypatch.setattr(cm, "CONTRACT_SCHEMA_VERSION", "story-system/v2")
    path = _write_contract(tmp_path, "reviews/chapter_001.review.json", {"schema_version": "story-system/v1"})

    report = migrate_contracts_if_needed(tmp_path)

    assert report["migrated"] == []
    assert report["errors"], "缺少迁移函数应记录错误"
    # 文件保持旧版本，未损坏
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["meta"]["schema_version"] == "story-system/v1"


def test_unknown_newer_version_skipped_safely(tmp_path):
    path = _write_contract(tmp_path, "MASTER_SETTING.json", {"schema_version": "story-system/v99"})

    report = migrate_contracts_if_needed(tmp_path)

    assert report["migrated"] == []
    assert len(report["skipped_unknown"]) == 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["meta"]["schema_version"] == "story-system/v99"


def test_no_version_field_treated_as_v1(tmp_path):
    path = _write_contract(tmp_path, "MASTER_SETTING.json", {"contract_type": "MASTER_SETTING"})

    report = migrate_contracts_if_needed(tmp_path)

    # 当前为 v1，无版本字段视为 v1，无需迁移
    assert report["migrated"] == []
    assert report["errors"] == []


def test_empty_project_has_no_side_effect(tmp_path):
    report = migrate_contracts_if_needed(tmp_path)

    assert report["migrated"] == []
    assert report["backed_up"] == []
    assert report["errors"] == []
