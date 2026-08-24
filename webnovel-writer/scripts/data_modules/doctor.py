#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .config import DataModulesConfig
from .db import connect
from .project_phase import (
    INIT_REQUIRED_DIRS,
    INIT_REQUIRED_FILES,
    PHASE_INIT_READY,
    PHASE_INIT_SCAFFOLDED,
    PHASE_NO_PROJECT,
    ProjectPhaseSnapshot,
    contract_files_for_chapter,
    resolve_project_phase,
)
from .projection_log import (
    latest_projection_run,
    projection_log_path,
    projection_run_failed,
    projection_run_pending,
)
from .story_runtime_health import build_story_runtime_health


SCHEMA_VERSION = "webnovel-doctor/v1"
CHECK_OK = "ok"
CHECK_WARNING = "warning"
CHECK_ERROR = "error"
CHECK_SKIPPED = "skipped"


def _check(
    check_id: str,
    *,
    status: str,
    severity: str,
    message: str,
    path: str = "",
    expected: str = "",
    actual: str = "",
    impact: str = "",
    repair: str = "",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status,
        "severity": severity,
        "message": message,
        "path": path,
        "expected": expected,
        "actual": actual,
        "impact": impact,
        "repair": repair,
    }


def _rel(project_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "missing"
    except json.JSONDecodeError as exc:
        return {}, f"invalid json: {exc}"
    except OSError as exc:
        return {}, f"read error: {exc}"
    if not isinstance(payload, dict):
        return {}, "json root is not object"
    return payload, ""


def _expected_profile(snapshot: ProjectPhaseSnapshot) -> dict[str, Any]:
    expected_files = list(INIT_REQUIRED_FILES)
    expected_dirs = list(INIT_REQUIRED_DIRS)
    if snapshot.phase not in {PHASE_NO_PROJECT, PHASE_INIT_SCAFFOLDED, PHASE_INIT_READY}:
        expected_files.extend(snapshot.missing_contract_files)
    if snapshot.target_chapter > 0 and snapshot.phase not in {PHASE_NO_PROJECT, PHASE_INIT_SCAFFOLDED, PHASE_INIT_READY}:
        expected_files.extend(
            str(path.relative_to(Path(snapshot.project_root)))
            for path in contract_files_for_chapter(Path(snapshot.project_root), snapshot.target_chapter).values()
        )
    return {
        "phase": snapshot.phase,
        "target_chapter": snapshot.target_chapter,
        "files": sorted(set(expected_files)),
        "dirs": sorted(set(expected_dirs)),
    }


def _preflight_checks(preflight_report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not preflight_report:
        return []
    checks: list[dict[str, Any]] = []
    for item in preflight_report.get("checks") or []:
        if not isinstance(item, dict):
            continue
        ok = bool(item.get("ok"))
        name = str(item.get("name") or "unknown")
        checks.append(
            _check(
                f"preflight.{name}",
                status=CHECK_OK if ok else CHECK_ERROR,
                severity="info" if ok else "blocker",
                message=f"preflight {name} {'ok' if ok else 'failed'}",
                path=str(item.get("path") or ""),
                actual=str(item.get("error") or ""),
                impact="" if ok else "统一 CLI 或项目解析可能不可用。",
                repair="" if ok else "先修复 preflight 输出的路径或 project_root 问题。",
            )
        )
    return checks


def _file_checks(project_root: Path, snapshot: ProjectPhaseSnapshot) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for rel in INIT_REQUIRED_DIRS:
        path = project_root / rel
        exists = path.is_dir()
        checks.append(
            _check(
                f"file.dir.{rel}",
                status=CHECK_OK if exists else CHECK_ERROR,
                severity="info" if exists else "blocker",
                message=f"required directory {rel}",
                path=str(path),
                expected="directory exists",
                actual="exists" if exists else "missing",
                impact="" if exists else "项目骨架不完整，后续写作/备份/报告可能写入失败。",
                repair="" if exists else "重新运行 /webnovel-init，或手动创建该目录后再运行 doctor。",
            )
        )
    for rel in INIT_REQUIRED_FILES:
        path = project_root / rel
        exists = path.is_file()
        checks.append(
            _check(
                f"file.required.{rel}",
                status=CHECK_OK if exists else CHECK_ERROR,
                severity="info" if exists else "blocker",
                message=f"required file {rel}",
                path=str(path),
                expected="file exists",
                actual="exists" if exists else "missing",
                impact="" if exists else "项目初始化产物缺失，当前阶段判断和后续流程会不可靠。",
                repair="" if exists else "使用 /webnovel-init 补齐项目骨架，或按 init_project.py 模板补齐文件。",
            )
        )

    if snapshot.phase not in {PHASE_NO_PROJECT, PHASE_INIT_SCAFFOLDED, PHASE_INIT_READY} and snapshot.target_chapter > 0:
        for name, path in contract_files_for_chapter(project_root, snapshot.target_chapter).items():
            exists = path.is_file()
            checks.append(
                _check(
                    f"file.contract.{name}",
                    status=CHECK_OK if exists else CHECK_ERROR,
                    severity="info" if exists else "blocker",
                    message=f"story contract {name}",
                    path=str(path),
                    expected="file exists",
                    actual="exists" if exists else "missing",
                    impact="" if exists else "写章上下文缺少主链合同，容易用旧 state 或旧大纲写偏。",
                    repair="" if exists else "运行 webnovel.py story-system ... --persist --emit-runtime-contracts --chapter N。",
                )
            )
    return checks


def _json_checks(project_root: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    json_files = [
        project_root / ".webnovel" / "state.json",
        project_root / ".story-system" / "MASTER_SETTING.json",
    ]

    # P1-7：判断是否已是「写多章项目」——此时 MASTER_SETTING 缺失应升级为 error
    state_path = project_root / ".webnovel" / "state.json"
    has_chapters = False
    if state_path.is_file():
        state_payload, _ = _read_json(state_path)
        if isinstance(state_payload, dict):
            progress = state_payload.get("progress") or {}
            current_chapter = int(progress.get("current_chapter") or 0)
            has_chapters = current_chapter > 0

    for path in json_files:
        if not path.exists():
            # P1-7：MASTER_SETTING 缺失时，若已写多章则升级为 error（不再是 SKIPPED）
            is_master = path.name == "MASTER_SETTING.json"
            status = CHECK_ERROR if (is_master and has_chapters) else CHECK_SKIPPED
            severity = "blocker" if (is_master and has_chapters) else "info"
            checks.append(
                _check(
                    f"json.{_rel(project_root, path)}",
                    status=status,
                    severity=severity,
                    message=f"{_rel(project_root, path)} not present",
                    path=str(path),
                    expected="valid JSON object when present",
                    actual="missing",
                    impact="" if not (is_master and has_chapters) else "已写多章但 MASTER_SETTING 缺失，合同体系断裂，写章/检索/续写都会受影响。",
                    repair="" if not (is_master and has_chapters) else "运行 story-system --persist 重建 MASTER_SETTING，或从 git/backup 恢复。",
                )
            )
            continue
        payload, error = _read_json(path)
        checks.append(
            _check(
                f"json.{_rel(project_root, path)}",
                status=CHECK_OK if not error else CHECK_ERROR,
                severity="info" if not error else "blocker",
                message=f"{_rel(project_root, path)} json parse",
                path=str(path),
                expected="valid JSON object",
                actual="ok" if not error else error,
                impact="" if not error else "JSON 无法读取会导致 CLI、dashboard 或状态推导失败。",
                repair="" if not error else "用 UTF-8 修复 JSON 格式；必要时从 git/backup 恢复。",
            )
        )
        if path.name == "state.json" and not error:
            for key in ("project_info", "progress"):
                checks.append(
                    _check(
                        f"json.state.{key}",
                        status=CHECK_OK if isinstance(payload.get(key), dict) else CHECK_WARNING,
                        severity="info" if isinstance(payload.get(key), dict) else "warning",
                        message=f"state.json contains {key}",
                        path=str(path),
                        expected="object field",
                        actual=type(payload.get(key)).__name__,
                        impact="" if isinstance(payload.get(key), dict) else "旧项目或手改 state 可能缺少运行时字段。",
                        repair="" if isinstance(payload.get(key), dict) else "运行 webnovel.py init 到同一目录可增量补齐 schema。",
                    )
                )

    # P1-7：扩展校验合同体系 JSON 合法性（volumes/chapters/reviews）
    checks.extend(_contract_json_checks(project_root))
    return checks


def _contract_json_checks(project_root: Path) -> list[dict[str, Any]]:
    """P1-7：校验 .story-system 下合同 JSON 合法性（此前只查 MASTER_SETTING）。"""
    checks: list[dict[str, Any]] = []
    story_root = project_root / ".story-system"
    contract_dirs = [
        ("volumes", "volume_*.json"),
        ("chapters", "chapter_*.json"),
        ("reviews", "chapter_*.review.json"),
    ]
    for sub_dir, pattern in contract_dirs:
        target_dir = story_root / sub_dir
        if not target_dir.is_dir():
            continue
        files = sorted(target_dir.glob(pattern))
        if not files:
            continue
        broken = []
        for path in files:
            _, error = _read_json(path)
            if error:
                broken.append({"path": _rel(project_root, path), "error": error})
        check_id = f"json.contracts.{sub_dir}"
        if broken:
            checks.append(
                _check(
                    check_id,
                    status=CHECK_ERROR,
                    severity="blocker",
                    message=f"{sub_dir}/ 下 {len(broken)} 个合同 JSON 损坏",
                    path=str(target_dir),
                    expected=f"{len(files)} 个合法 JSON",
                    actual=f"broken={broken[:3]}",
                    impact="损坏的合同会导致 story-system 解析失败，影响写章上下文与续写。",
                    repair="用 UTF-8 修复 JSON 格式；必要时从 git/backup 恢复。",
                )
            )
        else:
            checks.append(
                _check(
                    check_id,
                    status=CHECK_OK,
                    severity="info",
                    message=f"{sub_dir}/ 下 {len(files)} 个合同 JSON 合法",
                    path=str(target_dir),
                    expected=f"{len(files)} 个合法 JSON",
                    actual=f"{len(files)} files ok",
                )
            )
    return checks


def _sqlite_table_count(path: Path, table: str) -> tuple[bool, int, str]:
    if not path.is_file():
        return False, 0, "missing"
    try:
        with connect(path) as conn:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not row:
                return False, 0, "table_missing"
            count_row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            return True, int(count_row[0] or 0) if count_row else 0, ""
    except sqlite3.Error as exc:
        return False, 0, str(exc)


def _sqlite_checks(project_root: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    cfg = DataModulesConfig.from_project_root(project_root)
    # P1-7：扩展 index_db 检查范围——entities/relationships/state_changes
    # 此前只查 chapters 表，遗漏实体图谱与状态变更完整性
    for db_path, table, check_id, impact in (
        (cfg.index_db, "chapters", "sqlite.index_db.chapters", "查询、关系图谱和 dashboard 章节统计会降级。"),
        (cfg.index_db, "entities", "sqlite.index_db.entities", "实体查询、角色卡和 dashboard 角色统计会降级。"),
        (cfg.index_db, "relationships", "sqlite.index_db.relationships", "关系图谱查询不可用，影响角色关系追溯。"),
        (cfg.index_db, "state_changes", "sqlite.index_db.state_changes", "状态演进查询不可用，影响 continuity 校验。"),
        (cfg.vector_db, "vectors", "sqlite.vector_db.vectors", "RAG 向量召回不可用，会退化为关键词或空召回。"),
    ):
        exists = db_path.is_file()
        table_ok, count, error = _sqlite_table_count(db_path, table)
        if not exists:
            checks.append(
                _check(
                    check_id,
                    status=CHECK_WARNING,
                    severity="warning",
                    message=f"{db_path.name} missing",
                    path=str(db_path),
                    expected=f"sqlite db with {table} table",
                    actual="missing",
                    impact=impact,
                    repair="运行对应 index/rag 命令生成数据库；init 刚结束时可暂时忽略。",
                )
            )
            continue
        checks.append(
            _check(
                check_id,
                status=CHECK_OK if table_ok else CHECK_WARNING,
                severity="info" if table_ok else "warning",
                message=f"{db_path.name}.{table}",
                path=str(db_path),
                expected=f"{table} table readable",
                actual=f"rows={count}" if table_ok else error,
                impact="" if table_ok else impact,
                repair="" if table_ok else "重新运行索引/RAG 构建命令；若 sqlite 损坏，从备份恢复。",
            )
        )

    # P1-9 修复：vectors 表 embedding 完整性扫描——统计 embedding 为 NULL 的行
    # （embedding 失败只写了 fallback 正文行，语义检索缺失，仅 BM25 可用）。
    vector_db = cfg.vector_db
    if vector_db.is_file():
        null_count = _sqlite_null_embedding_count(vector_db)
        if null_count is None:
            return checks
        if null_count > 0:
            checks.append(
                _check(
                    "sqlite.vector_db.embedding_null",
                    status=CHECK_WARNING,
                    severity="warning",
                    message=f"vectors 表有 {null_count} 个 chunk 缺少语义向量（embedding 失败）",
                    path=str(vector_db),
                    expected="所有 chunk 均有 embedding",
                    actual=f"embedding 为 NULL 的行数={null_count}",
                    impact="这些 chunk 只能关键词（BM25）检索，语义检索缺失。",
                    repair="确认 embedding API 可用后，对该书项目补跑 projections replay（或重跑受影响章节）。",
                )
            )
    return checks


def _sqlite_null_embedding_count(db_path: Path) -> int | None:
    """统计 vectors 表中 embedding 为 NULL 的行数；表缺失或读取出错返回 None。"""
    try:
        import sqlite3

        with connect(db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='vectors'"
            ).fetchone()
            if not row:
                return None
            count_row = conn.execute(
                "SELECT COUNT(*) FROM vectors WHERE embedding IS NULL"
            ).fetchone()
            return int(count_row[0] or 0) if count_row else 0
    except sqlite3.Error:
        return None


def _rag_checks(project_root: Path) -> list[dict[str, Any]]:
    cfg = DataModulesConfig.from_project_root(project_root)
    checks: list[dict[str, Any]] = []
    for key, present, base_url, model in (
        ("embed", bool(str(cfg.embed_api_key or "").strip()), cfg.embed_base_url, cfg.embed_model),
        ("rerank", bool(str(cfg.rerank_api_key or "").strip()), cfg.rerank_base_url, cfg.rerank_model),
    ):
        checks.append(
            _check(
                f"rag.{key}.api_key",
                status=CHECK_OK if present else CHECK_WARNING,
                severity="info" if present else "warning",
                message=f"{key} api key configured",
                expected="api key present in env or .env",
                actual=f"present; model={model}; base_url={base_url}" if present else f"missing; model={model}; base_url={base_url}",
                impact="" if present else "RAG 相关调用会不可用或降级。",
                repair="" if present else "复制 .env.example 为 .env，并填写对应 API key；不要把真实 key 提交到仓库。",
            )
        )
    return checks


def _projection_log_checks(project_root: Path, snapshot: ProjectPhaseSnapshot) -> list[dict[str, Any]]:
    log_path = projection_log_path(project_root)
    latest_commit = snapshot.latest_commit
    if latest_commit is None:
        return [
            _check(
                "projection_log.present",
                status=CHECK_SKIPPED,
                severity="info",
                message="no commit yet; projection log not required",
                path=str(log_path),
                expected="projection log after first commit",
                actual="no commit",
            )
        ]
    if not log_path.is_file():
        return [
            _check(
                "projection_log.present",
                status=CHECK_WARNING,
                severity="warning",
                message="projection log missing for project with commits",
                path=str(log_path),
                expected="projection_log.jsonl exists after projection run",
                actual="missing",
                impact="无法从独立执行日志定位历史 projection run；仍可兼容读取 commit 内 projection_status。",
                repair="后续 chapter-commit 会自动双写 projection_log；旧项目可暂时忽略。",
            )
        ]
    latest = latest_projection_run(project_root, chapter=latest_commit.chapter)
    if not latest:
        return [
            _check(
                "projection_log.latest_run",
                status=CHECK_WARNING,
                severity="warning",
                message="projection log has no run for latest commit",
                path=str(log_path),
                expected=f"run for chapter {latest_commit.chapter}",
                actual="missing",
                impact="最新 commit 的投影执行历史不可见。",
                repair="后续 projection retry/replay 可补齐；当前仍兼容 commit 内 projection_status。",
            )
        ]
    failed = projection_run_failed(latest)
    pending = projection_run_pending(latest)
    status_ok = not failed and not pending
    return [
        _check(
            "projection_log.latest_run",
            status=CHECK_OK if status_ok else CHECK_ERROR,
            severity="info" if status_ok else "blocker",
            message="latest projection log run",
            path=str(log_path),
            expected="latest run status done/skipped",
            actual=f"chapter={latest.get('chapter')} status={latest.get('status')}",
            impact="read-model 投影失败或未完成，需要补跑。" if not status_ok else "",
            repair="查看 projection_log.jsonl 的 writers 字段，修复后补跑 projection retry/replay。" if not status_ok else "",
        )
    ]


def _extraction_warnings_check(project_root: Path, snapshot: ProjectPhaseSnapshot) -> list[dict[str, Any]]:
    """抽查最新 accepted commit 的 extraction_warnings：非空则提示提取质量信号。

    P0-4 第三步：把 data-agent 提取时的轻校验告警（章号不可解析、事件章号
    不符、状态/实体字段缺失等）在 doctor 体检里透出，供作者识别是否需要
    memory-correction 纠错。
    """
    latest_commit = snapshot.latest_commit
    if latest_commit is None or latest_commit.status != "accepted":
        return [
            _check(
                "commit.extraction_warnings",
                status=CHECK_SKIPPED,
                severity="info",
                message="no accepted commit to inspect extraction warnings",
                path=str(project_root / ".story-system" / "commits"),
                expected="accepted commit with extraction_warnings",
                actual="no accepted commit",
            )
        ]

    commit_path = Path(latest_commit.path) if latest_commit.path else (
        project_root / ".story-system" / "commits" / f"chapter_{latest_commit.chapter:03d}.commit.json"
    )
    payload, error = _read_json(commit_path)
    if error:
        return [
            _check(
                "commit.extraction_warnings",
                status=CHECK_WARNING,
                severity="warning",
                message="latest accepted commit unreadable",
                path=str(commit_path),
                expected="readable commit json",
                actual=error,
                impact="无法抽查提取质量信号。",
                repair="检查 commit json 是否损坏。",
            )
        ]

    meta = payload.get("meta") if isinstance(payload, dict) else {}
    warnings = meta.get("extraction_warnings") if isinstance(meta, dict) else None
    if not warnings:
        return [
            _check(
                "commit.extraction_warnings",
                status=CHECK_OK,
                severity="info",
                message="latest accepted commit has no extraction warnings",
                path=str(commit_path),
                expected="extraction_warnings empty",
                actual="empty",
            )
        ]

    codes = sorted({str(w.get("code") or "unknown") for w in warnings if isinstance(w, dict)})
    return [
        _check(
            "commit.extraction_warnings",
            status=CHECK_WARNING,
            severity="warning",
            message=f"latest accepted commit has {len(warnings)} extraction warning(s)",
            path=str(commit_path),
            expected="extraction_warnings empty",
            actual=f"codes={codes}",
            impact="提取质量有缺口：可能有章号不可解析、事件章号不符或字段缺失，记忆库可能存入了错误或缺失事实。",
            repair="用 webnovel.py memory correct 修正对应记忆条目，或重跑该章的 data-agent 提取。",
        )
    ]


def _contract_version_checks(project_root: Path) -> list[dict[str, Any]]:
    """P1-2：检查合同 schema 版本是否落后于当前版本，提示运行迁移。"""
    from .contract_migrations import (
        CONTRACT_SCHEMA_VERSION as _CURRENT,
        _iter_contract_files,
        _parse_version,
    )

    files = _iter_contract_files(project_root)
    if not files:
        return [
            _check(
                "contract.schema_version",
                status=CHECK_SKIPPED,
                severity="info",
                message="no story-system contract files to version-check",
                path=str(project_root / ".story-system"),
                expected="contract json files with meta.schema_version",
                actual="missing",
            )
        ]

    current = _parse_version(_CURRENT)
    outdated: list[str] = []
    unknown: list[str] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        meta = payload.get("meta") if isinstance(payload, dict) else {}
        version_str = str(meta.get("schema_version") or "") if isinstance(meta, dict) else ""
        version = _parse_version(version_str)
        if version == 0:
            # 无版本号视为 v1；当前为 v1 时不告警，未来升 v2 时视为落后。
            version = 1
        if 0 < version < current:
            outdated.append(_rel(project_root, path))
        elif version > current:
            unknown.append(_rel(project_root, path))

    if outdated:
        return [
            _check(
                "contract.schema_version",
                status=CHECK_WARNING,
                severity="warning",
                message=f"{len(outdated)} 个合同文件 schema 版本落后于 {_CURRENT}",
                path=str(project_root / ".story-system"),
                expected=f"all contracts at {_CURRENT}",
                actual="outdated=" + ",".join(outdated[:5]),
                impact="旧版本合同可能缺少新字段，读取/写入时结构不兼容。",
                repair="运行 story-system 写入（--persist/--emit-runtime-contracts）会自动触发迁移；或调用 contract_migrations.migrate_contracts_if_needed。",
            )
        ]
    if unknown:
        return [
            _check(
                "contract.schema_version",
                status=CHECK_WARNING,
                severity="warning",
                message=f"{len(unknown)} 个合同文件 schema 版本高于当前版本 {_CURRENT}",
                path=str(project_root / ".story-system"),
                expected=f"contracts at {_CURRENT}",
                actual="unknown=" + ",".join(unknown[:5]),
                impact="文件可能由更新版本插件生成，当前插件无法识别其结构。",
                repair="升级插件到对应版本，或手动检查这些合同文件。",
            )
        ]
    return [
        _check(
            "contract.schema_version",
            status=CHECK_OK,
            severity="info",
            message=f"all contract files at {_CURRENT}",
            path=str(project_root / ".story-system"),
            expected=f"contracts at {_CURRENT}",
            actual=f"{len(files)} files ok",
        )
    ]


def _run_log_checks(project_root: Path) -> list[dict[str, Any]]:
    """P1-6 诊断：检查 run_last.log 是否只有 write-start 一条（未追加关键步骤）。

    P1-7：同时检查 run_last.log 是否存在（init/plan 阶段可缺失，写章后应存在）。
    """
    log_path = project_root / ".webnovel" / "logs" / "run_last.log"
    if not log_path.is_file():
        return [
            _check(
                "run_log.existence",
                status=CHECK_SKIPPED,
                severity="info",
                message="run_last.log not present (init/plan 阶段正常)",
                path=str(log_path),
                expected="run_last.log after write-start",
                actual="missing",
            )
        ]

    try:
        content = log_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [
            _check(
                "run_log.existence",
                status=CHECK_ERROR,
                severity="blocker",
                message=f"run_last.log 读取失败: {exc}",
                path=str(log_path),
                expected="readable text log",
                actual=str(exc),
            )
        ]

    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    if not lines:
        return [
            _check(
                "run_log.existence",
                status=CHECK_WARNING,
                severity="warning",
                message="run_last.log 为空",
                path=str(log_path),
                expected="非空日志",
                actual="empty",
            )
        ]

    # P1-6：只有 write-start 一条 → 未追加关键步骤日志，崩溃后无法定位断点
    has_write_start = any("write-start" in ln for ln in lines)
    has_step_logs = any(
        any(event in ln for event in ("step-env", "step-context", "step-draft", "step-review", "step-data", "step-commit"))
        for ln in lines
    )
    if has_write_start and not has_step_logs and len(lines) <= 2:
        return [
            _check(
                "run_log.step_coverage",
                status=CHECK_WARNING,
                severity="warning",
                message="run_last.log 只有 write-start，未追加关键步骤日志",
                path=str(log_path),
                expected="write-start + 各关键步骤追加日志",
                actual=f"{len(lines)} 行（仅 write-start）",
                impact="P1-6：写章崩溃后 run_last.log 无法定位最后卡点，排障困难。",
                repair="确认 SKILL 按规范在每个关键步骤后调用 run-log --event <step> --append。",
            )
        ]
    return [
        _check(
            "run_log.step_coverage",
            status=CHECK_OK,
            severity="info",
            message=f"run_last.log 含 {len(lines)} 行，关键步骤日志覆盖正常",
            path=str(log_path),
            expected="write-start + 各关键步骤追加日志",
            actual=f"{len(lines)} 行",
        )
    ]


def _python_checks() -> list[dict[str, Any]]:
    checks = [
        _check(
            "python.version",
            status=CHECK_OK if sys.version_info >= (3, 10) else CHECK_ERROR,
            severity="info" if sys.version_info >= (3, 10) else "blocker",
            message="python version",
            expected=">= 3.10",
            actual=platform.python_version(),
            impact="" if sys.version_info >= (3, 10) else "运行时依赖 Python 3.10+ 语法和库行为。",
            repair="" if sys.version_info >= (3, 10) else "切换到 Python 3.10 或更高版本。",
        )
    ]
    for module_name in ("aiohttp", "filelock", "pydantic"):
        found = importlib.util.find_spec(module_name) is not None
        checks.append(
            _check(
                f"python.import.{module_name}",
                status=CHECK_OK if found else CHECK_ERROR,
                severity="info" if found else "blocker",
                message=f"import {module_name}",
                expected="module importable",
                actual="present" if found else "missing",
                impact="" if found else "核心数据模块可能无法运行。",
                repair="" if found else "运行 python -m pip install -r scripts/requirements.txt。",
            )
        )
    for module_name in ("fastapi", "uvicorn", "watchdog"):
        found = importlib.util.find_spec(module_name) is not None
        checks.append(
            _check(
                f"python.import.dashboard.{module_name}",
                status=CHECK_OK if found else CHECK_WARNING,
                severity="info" if found else "warning",
                message=f"import {module_name}",
                expected="module importable for dashboard",
                actual="present" if found else "missing",
                impact="" if found else "Dashboard 服务端可能无法启动。",
                repair="" if found else "运行 python -m pip install -r dashboard/requirements.txt。",
            )
        )
    return checks


def _dashboard_checks(plugin_root: Path | None = None) -> list[dict[str, Any]]:
    if plugin_root is None:
        plugin_root = Path(__file__).resolve().parents[2]
    dashboard_root = plugin_root / "dashboard"
    dist = dashboard_root / "frontend" / "dist"
    package_json = dashboard_root / "frontend" / "package.json"
    requirements = dashboard_root / "requirements.txt"
    checks: list[dict[str, Any]] = []
    for check_id, path, expected in (
        ("dashboard.root", dashboard_root, "directory exists"),
        ("dashboard.frontend.dist", dist, "built frontend dist exists"),
        ("dashboard.frontend.package_json", package_json, "package.json exists"),
        ("dashboard.requirements", requirements, "requirements.txt exists"),
    ):
        exists = path.is_dir() if expected.startswith("directory") or path == dist else path.is_file()
        checks.append(
            _check(
                check_id,
                status=CHECK_OK if exists else CHECK_WARNING,
                severity="info" if exists else "warning",
                message=check_id,
                path=str(path),
                expected=expected,
                actual="exists" if exists else "missing",
                impact="" if exists else "Dashboard 可能无法打开或发布包缺少前端产物。",
                repair="" if exists else "按 dashboard 文档安装/构建前端，或检查发布包是否遗漏 dist。",
            )
        )
    return checks


def build_doctor_report(
    project_root: str | Path | None,
    *,
    chapter: int | None = None,
    deep: bool = False,
    preflight_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = resolve_project_phase(project_root, chapter=chapter)
    checks: list[dict[str, Any]] = []
    checks.extend(_preflight_checks(preflight_report))

    if snapshot.phase == PHASE_NO_PROJECT or not snapshot.project_root:
        checks.append(
            _check(
                "project.root",
                status=CHECK_ERROR,
                severity="blocker",
                message="project root not resolved",
                path=str(project_root or ""),
                expected=".webnovel/state.json",
                actual="missing",
                impact="无法判断项目状态，也不能安全运行写作链路。",
                repair="先运行 /webnovel-init，或运行 webnovel.py use <project_root> 绑定已有项目。",
            )
        )
    else:
        root = Path(snapshot.project_root)
        checks.extend(_file_checks(root, snapshot))
        checks.extend(_json_checks(root))
        try:
            runtime_health = build_story_runtime_health(root, chapter=chapter)
        except Exception as exc:
            runtime_health = {"error": str(exc)}
            checks.append(
                _check(
                    "story_runtime.health",
                    status=CHECK_WARNING,
                    severity="warning",
                    message="story runtime health failed",
                    actual=str(exc),
                    impact="Story System 主链健康摘要不可用。",
                    repair="检查 .story-system 合同与 commit JSON 是否可读。",
                )
            )
        else:
            checks.append(
                _check(
                    "story_runtime.health",
                    status=CHECK_OK if runtime_health.get("mainline_ready") else CHECK_WARNING,
                    severity="info" if runtime_health.get("mainline_ready") else "warning",
                    message="story runtime health",
                    expected="mainline_ready true when writing stage",
                    actual=json.dumps(runtime_health, ensure_ascii=False),
                    impact="" if runtime_health.get("mainline_ready") else "当前章节可能会使用 fallback source。",
                    repair="" if runtime_health.get("mainline_ready") else "补齐 Story System 合同和 accepted commit 后再写。",
                )
            )
        checks.extend(_sqlite_checks(root))
        checks.extend(_projection_log_checks(root, snapshot))
        checks.extend(_extraction_warnings_check(root, snapshot))
        checks.extend(_contract_version_checks(root))
        checks.extend(_run_log_checks(root))
        checks.extend(_rag_checks(root))

    checks.extend(_python_checks())
    if deep:
        checks.extend(_dashboard_checks())

    blocking = [item for item in checks if item["severity"] == "blocker" and item["status"] == CHECK_ERROR]
    warnings = [item for item in checks if item["status"] == CHECK_WARNING]
    recommended_actions = [item["repair"] for item in checks if item.get("repair")]
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": not blocking,
        "project_root": snapshot.project_root,
        "mode": "deep" if deep else "standard",
        "phase": snapshot.phase,
        "expected_profile": _expected_profile(snapshot),
        "blocking_count": len(blocking),
        "warning_count": len(warnings),
        "checks": checks,
        "recommended_actions": list(dict.fromkeys(recommended_actions)),
    }


def format_doctor_report(report: dict[str, Any], output_format: str = "text") -> str:
    if output_format == "json":
        return json.dumps(report, ensure_ascii=False, indent=2)
    status = "OK" if report.get("ok") else "ERROR"
    lines = [
        f"{status} webnovel-doctor",
        f"project_root: {report.get('project_root') or '(未解析)'}",
        f"phase: {report.get('phase')}",
        f"blocking: {report.get('blocking_count')} warnings: {report.get('warning_count')}",
    ]
    for item in report.get("checks") or []:
        if item.get("status") == CHECK_OK:
            continue
        lines.append(f"{str(item.get('status')).upper()} {item.get('id')}: {item.get('message')}")
        if item.get("path"):
            lines.append(f"  path: {item.get('path')}")
        if item.get("actual"):
            lines.append(f"  actual: {item.get('actual')}")
        if item.get("impact"):
            lines.append(f"  impact: {item.get('impact')}")
        if item.get("repair"):
            lines.append(f"  repair: {item.get('repair')}")
    actions = report.get("recommended_actions") or []
    if actions:
        lines.append("recommended_actions:")
        lines.extend(f"- {action}" for action in actions[:8])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run read-only webnovel project doctor")
    parser.add_argument("--project-root", default="", help="书项目根目录")
    parser.add_argument("--chapter", type=int, default=None, help="目标章节号")
    parser.add_argument("--deep", action="store_true", help="包含 dashboard 等较深检查")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    report = build_doctor_report(args.project_root or None, chapter=args.chapter, deep=args.deep)
    print(format_doctor_report(report, args.format))
    raise SystemExit(0 if report.get("ok") else 1)


if __name__ == "__main__":
    main()

