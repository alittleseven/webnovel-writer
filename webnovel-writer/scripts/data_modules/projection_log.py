#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


SCHEMA_VERSION = "webnovel-projection-log/v1"
PROJECTION_LOG_REL = Path(".webnovel") / "projection_log.jsonl"


def projection_log_path(project_root: str | Path) -> Path:
    return Path(project_root) / PROJECTION_LOG_REL


def commit_hash(commit_payload: dict[str, Any]) -> str:
    raw = json.dumps(commit_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _overall_status(writers: dict[str, dict[str, Any]]) -> str:
    statuses = {str(item.get("status") or "") for item in writers.values()}
    if any(status.startswith("failed") or status == "failed" for status in statuses):
        return "failed"
    if "pending" in statuses:
        return "pending"
    # P1-9b：存在 partial（部分 embedding 失败但 BM25 可用）时，run 级状态
    # 透出 partial，而非吞成 done。failed/pending 仍优先（更严重）。
    if "partial" in statuses:
        return "partial"
    if statuses and statuses <= {"skipped"}:
        return "skipped"
    return "done"


def build_projection_run(
    *,
    project_root: str | Path,
    commit_payload: dict[str, Any],
    writer_results: dict[str, dict[str, Any]],
    commit_path: str | Path | None = None,
) -> dict[str, Any]:
    meta = commit_payload.get("meta") if isinstance(commit_payload, dict) else {}
    chapter = int((meta or {}).get("chapter") or 0)
    if commit_path is None and chapter > 0:
        commit_path = Path(project_root) / ".story-system" / "commits" / f"chapter_{chapter:03d}.commit.json"
    writers = {str(name): dict(result) for name, result in writer_results.items()}
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": uuid4().hex,
        "created_at": _now_iso(),
        "chapter": chapter,
        "commit_path": str(commit_path or ""),
        "commit_hash": commit_hash(commit_payload),
        "commit_status": str((meta or {}).get("status") or ""),
        "status": _overall_status(writers),
        "writers": writers,
        "projection_status": dict(commit_payload.get("projection_status") or {}),
    }


def projection_status_from_run(run: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(run, dict):
        return {}
    writers = run.get("writers")
    if isinstance(writers, dict):
        statuses = {
            str(name): str(result.get("status") or "")
            for name, result in writers.items()
            if isinstance(result, dict) and result.get("status")
        }
        if statuses:
            return statuses
    projection_status = run.get("projection_status")
    if isinstance(projection_status, dict):
        return {str(name): str(status) for name, status in projection_status.items()}
    return {}


def projection_run_failed(run: dict[str, Any] | None) -> bool:
    if not isinstance(run, dict):
        return False
    if str(run.get("status") or "").startswith("failed"):
        return True
    return any(status.startswith("failed") for status in projection_status_from_run(run).values())


def projection_run_pending(run: dict[str, Any] | None) -> bool:
    if not isinstance(run, dict):
        return False
    if str(run.get("status") or "") == "pending":
        return True
    return any(status == "pending" for status in projection_status_from_run(run).values())


def append_projection_run(
    project_root: str | Path,
    commit_payload: dict[str, Any],
    writer_results: dict[str, dict[str, Any]],
    *,
    commit_path: str | Path | None = None,
) -> dict[str, Any]:
    record = build_projection_run(
        project_root=project_root,
        commit_payload=commit_payload,
        writer_results=writer_results,
        commit_path=commit_path,
    )
    path = projection_log_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        handle.write("\n")
    return record


def read_projection_runs(project_root: str | Path, *, chapter: int | None = None) -> list[dict[str, Any]]:
    path = projection_log_path(project_root)
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if chapter is not None:
            try:
                record_chapter = int(payload.get("chapter") or 0)
            except (TypeError, ValueError):
                continue
            if record_chapter != int(chapter):
                continue
        records.append(payload)
    return records


def latest_projection_run(project_root: str | Path, *, chapter: int | None = None) -> dict[str, Any] | None:
    records = read_projection_runs(project_root, chapter=chapter)
    return records[-1] if records else None
