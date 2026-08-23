#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合同 schema 版本检测与迁移框架。

P1-2：story-system 合同的 schema_version 从硬编码字符串演进为版本常量，
并提供统一的迁移入口。设计参考 RAG 的迁移机制（rag_schema_meta +
检测旧版本触发迁移 + 迁移前备份），但合同是 JSON 文件而非 SQLite 表，
因此采用「扫描 JSON → 检测 meta.schema_version → 备份 → 逐版本迁移 →
原子写回」的方式。

当前版本为 v1，迁移注册表为空（为 v2+ 预留）。任何未来结构变更都应：
1. 递增 story_contract_schema.CONTRACT_SCHEMA_VERSION；
2. 在 CONTRACT_MIGRATIONS 注册 from_version -> 迁移函数；
3. 迁移函数保持幂等，失败时从备份恢复。
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List

from .story_contract_schema import CONTRACT_SCHEMA_VERSION

try:
    from security_utils import atomic_write_json
except ImportError:  # pragma: no cover
    from scripts.security_utils import atomic_write_json

# 迁移注册表：key 为「源版本号」（int），value 为迁移函数
# （接收 payload dict，返回迁移后的 payload dict）。
# 例如未来 v2 时：CONTRACT_MIGRATIONS[1] = migrate_v1_to_v2
CONTRACT_MIGRATIONS: Dict[int, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}

# 参与版本检测的合同文件（相对 .story-system 的 glob 模式）。
# 注意：commit/events 文件的 meta 结构不同，不属于「合同 schema」范围。
CONTRACT_FILE_PATTERNS = (
    "MASTER_SETTING.json",
    "anti_patterns.json",
    "chapters/chapter_*.json",
    "volumes/volume_*.json",
    "reviews/chapter_*.review.json",
)

_VERSION_RE = re.compile(r"/v(\d+)$")


class ContractMigrationError(RuntimeError):
    """迁移失败（缺少迁移函数 / 迁移后校验失败）。"""


def _parse_version(version: str) -> int:
    """从 "story-system/vN" 提取版本号；无法解析返回 0。"""
    match = _VERSION_RE.search(str(version or ""))
    return int(match.group(1)) if match else 0


def _current_version() -> int:
    return _parse_version(CONTRACT_SCHEMA_VERSION)


def _iter_contract_files(project_root: Path) -> List[Path]:
    story_root = project_root / ".story-system"
    if not story_root.is_dir():
        return []
    files: List[Path] = []
    for pattern in CONTRACT_FILE_PATTERNS:
        files.extend(sorted(story_root.glob(pattern)))
    return [p for p in files if p.is_file()]


def _backup_contract(path: Path, from_version: int) -> Path:
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{path.name}.v{from_version}.{timestamp}.bak"
    shutil.copy2(path, backup_path)
    return backup_path


def _apply_migrations(payload: Dict[str, Any], from_version: int) -> Dict[str, Any]:
    """按迁移链逐版本升级 payload，直到当前版本。"""
    current = _current_version()
    migrated = payload
    version = from_version
    while version < current:
        step = CONTRACT_MIGRATIONS.get(version)
        if step is None:
            raise ContractMigrationError(
                f"缺少从 v{version} 到 v{version + 1} 的迁移函数"
            )
        migrated = step(migrated)
        version += 1
    return migrated


def migrate_contracts_if_needed(project_root: str | Path) -> Dict[str, Any]:
    """检测并迁移 .story-system 下旧版本合同文件。

    返回报告：
    - migrated: 已迁移的文件路径列表
    - backed_up: 已备份的文件路径列表
    - skipped_unknown: 版本高于当前版本的文件（安全跳过，不降级）
    - unchanged: 已是最新版本或无需迁移的文件数
    """
    root = Path(project_root).expanduser().resolve()
    current = _current_version()
    report: Dict[str, Any] = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "migrated": [],
        "backed_up": [],
        "skipped_unknown": [],
        "unchanged": 0,
        "errors": [],
    }

    for path in _iter_contract_files(root):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            report["errors"].append({"path": str(path), "error": f"读取失败: {exc}"})
            continue
        if not isinstance(payload, dict):
            report["unchanged"] += 1
            continue

        meta = payload.get("meta")
        version_str = str(meta.get("schema_version") or "") if isinstance(meta, dict) else ""
        from_version = _parse_version(version_str)
        if from_version == 0:
            # 无版本号：视为 v1（首批合同未写版本字段），按当前版本处理。
            from_version = 1 if current >= 1 else 0
        if from_version >= current:
            if from_version > current:
                report["skipped_unknown"].append(str(path))
            else:
                report["unchanged"] += 1
            continue

        backup_path = _backup_contract(path, from_version)
        report["backed_up"].append(str(backup_path))
        try:
            migrated = _apply_migrations(payload, from_version)
        except ContractMigrationError as exc:
            report["errors"].append({"path": str(path), "error": str(exc)})
            continue

        if isinstance(meta, dict):
            meta["schema_version"] = CONTRACT_SCHEMA_VERSION
        atomic_write_json(path, migrated, backup=True)
        report["migrated"].append(str(path))

    return report
