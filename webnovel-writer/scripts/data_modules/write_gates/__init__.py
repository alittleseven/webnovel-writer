#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "webnovel-write-gate/v1"
STAGES = ("prewrite", "precommit", "postcommit")


def issue(
    code: str,
    *,
    message: str,
    severity: str = "blocker",
    path: str = "",
    impact: str = "",
    repair: str = "",
    details: Any = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "path": path,
        "impact": impact,
        "repair": repair,
        "details": details,
    }


def gate_report(
    *,
    stage: str,
    project_root: str | Path,
    chapter: int,
    phase: str,
    errors: list[dict[str, Any]] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors = errors or []
    warnings = warnings or []
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": stage,
        "project_root": str(project_root),
        "chapter": chapter,
        "phase": phase,
        "ok": not any(item.get("severity") == "blocker" for item in errors),
        "errors": errors,
        "warnings": warnings,
        "details": details or {},
    }


def format_gate_report(report: dict[str, Any], output_format: str = "json") -> str:
    if output_format == "json":
        return json.dumps(report, ensure_ascii=False, indent=2)
    status = "OK" if report.get("ok") else "ERROR"
    lines = [
        f"{status} write-gate {report.get('stage')}",
        f"project_root: {report.get('project_root')}",
        f"chapter: {report.get('chapter')}",
        f"phase: {report.get('phase')}",
    ]
    for item in report.get("errors") or []:
        lines.append(f"ERROR {item.get('code')}: {item.get('message')}")
        if item.get("path"):
            lines.append(f"  path: {item.get('path')}")
        if item.get("impact"):
            lines.append(f"  impact: {item.get('impact')}")
        if item.get("repair"):
            lines.append(f"  repair: {item.get('repair')}")
    for item in report.get("warnings") or []:
        lines.append(f"WARNING {item.get('code')}: {item.get('message')}")
    return "\n".join(lines)


def _gate_codes(items: list[dict[str, Any]] | None) -> str:
    codes = [str(item.get("code") or "") for item in items or [] if isinstance(item, dict)]
    return ",".join(code for code in codes if code)


def format_gate_compact(report: dict[str, Any]) -> str:
    """一行结论：主对话只读结论，全量诊断见落盘快照（externalize_gate_report）。"""
    status = "OK" if report.get("ok") else "ERROR"
    errors = report.get("errors") or []
    warnings = report.get("warnings") or []
    parts = [
        status,
        f"write-gate {report.get('stage')}",
        f"chapter={report.get('chapter')}",
        f"phase={report.get('phase')}",
        f"errors={len(errors)}",
        f"warnings={len(warnings)}",
    ]
    error_codes = _gate_codes(errors)
    warning_codes = _gate_codes(warnings)
    if error_codes:
        parts.append(f"[{error_codes}]")
    if warning_codes:
        parts.append(f"({warning_codes})")
    parts.append(f"detail=.webnovel/tmp/last_gate_{report.get('stage')}.json")
    return " ".join(parts)


def externalize_gate_report(project_root: str | Path, report: dict[str, Any]) -> Path:
    """把完整门禁报告（含 story_runtime 等大对象）落盘，供程序按需读取。"""
    snapshot_path = (
        Path(project_root) / ".webnovel" / "tmp" / f"last_gate_{report.get('stage')}.json"
    )
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot_path


def run_write_gate(project_root: str | Path, *, chapter: int, stage: str) -> dict[str, Any]:
    if stage == "prewrite":
        from .prewrite import run_prewrite_gate

        return run_prewrite_gate(Path(project_root), chapter)
    if stage == "precommit":
        from .precommit import run_precommit_gate

        return run_precommit_gate(Path(project_root), chapter)
    if stage == "postcommit":
        from .postcommit import run_postcommit_gate

        return run_postcommit_gate(Path(project_root), chapter)
    raise ValueError(f"unknown write-gate stage: {stage}")
