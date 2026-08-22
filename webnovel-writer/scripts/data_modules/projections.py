#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .chapter_commit_service import ChapterCommitService
from .projection_log import latest_projection_run


SCHEMA_VERSION = "webnovel-projections/v1"
DEFAULT_PROJECTION_STATUS = {
    "state": "pending",
    "index": "pending",
    "summary": "pending",
    "memory": "pending",
    "vector": "pending",
}


def _commit_path(project_root: Path, chapter: int) -> Path:
    return project_root / ".story-system" / "commits" / f"chapter_{chapter:03d}.commit.json"


def _read_commit(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, "missing_commit"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, f"invalid_json:{exc}"
    except OSError as exc:
        return {}, f"read_error:{exc}"
    if not isinstance(payload, dict):
        return {}, "commit_not_object"
    payload.setdefault("projection_status", dict(DEFAULT_PROJECTION_STATUS))
    for key, value in DEFAULT_PROJECTION_STATUS.items():
        payload["projection_status"].setdefault(key, value)
    return payload, ""


def _projection_failed(payload: dict[str, Any]) -> bool:
    projection_status = payload.get("projection_status") or {}
    if not isinstance(projection_status, dict):
        return True
    return any(str(value).startswith("failed:") or str(value) == "pending" for value in projection_status.values())


def retry_projection(project_root: str | Path, *, chapter: int) -> dict[str, Any]:
    root = Path(project_root)
    path = _commit_path(root, chapter)
    payload, error = _read_commit(path)
    if error:
        return {
            "schema_version": SCHEMA_VERSION,
            "action": "retry",
            "ok": False,
            "project_root": str(root),
            "chapter": chapter,
            "error": error,
            "commit_path": str(path),
            "projection_status": {},
            "latest_projection_run": None,
        }

    service = ChapterCommitService(root)
    # 修复事件链崩溃窗口：retry 补跑时也要写 events + 生成修订提案，
    # 否则 commit persist 后崩溃会导致 events 文件与 amend 提案永久丢失、审计链断链。
    service.write_events_and_proposals(payload)
    projected = service.apply_projection_writers(payload)
    latest_run = latest_projection_run(root, chapter=chapter)
    return {
        "schema_version": SCHEMA_VERSION,
        "action": "retry",
        "ok": not _projection_failed(projected),
        "project_root": str(root),
        "chapter": chapter,
        "error": "",
        "commit_path": str(path),
        "projection_status": dict(projected.get("projection_status") or {}),
        "latest_projection_run": latest_run,
    }


def replay_projections(project_root: str | Path, *, start_chapter: int, end_chapter: int) -> dict[str, Any]:
    root = Path(project_root)
    if start_chapter <= 0 or end_chapter <= 0 or start_chapter > end_chapter:
        return {
            "schema_version": SCHEMA_VERSION,
            "action": "replay",
            "ok": False,
            "project_root": str(root),
            "start_chapter": start_chapter,
            "end_chapter": end_chapter,
            "error": "invalid_chapter_range",
            "results": [],
        }
    results = [retry_projection(root, chapter=chapter) for chapter in range(start_chapter, end_chapter + 1)]
    return {
        "schema_version": SCHEMA_VERSION,
        "action": "replay",
        "ok": all(item.get("ok") for item in results),
        "project_root": str(root),
        "start_chapter": start_chapter,
        "end_chapter": end_chapter,
        "error": "",
        "results": results,
    }


def format_projection_report(report: dict[str, Any], output_format: str = "json") -> str:
    if output_format == "json":
        return json.dumps(report, ensure_ascii=False, indent=2)
    status = "OK" if report.get("ok") else "ERROR"
    if report.get("action") == "retry":
        return "\n".join(
            [
                f"{status} projections retry",
                f"chapter: {report.get('chapter')}",
                f"commit_path: {report.get('commit_path')}",
                f"projection_status: {report.get('projection_status')}",
                f"error: {report.get('error') or ''}",
            ]
        )
    lines = [
        f"{status} projections replay",
        f"range: {report.get('start_chapter')}-{report.get('end_chapter')}",
        f"error: {report.get('error') or ''}",
    ]
    for item in report.get("results") or []:
        lines.append(f"- chapter {item.get('chapter')}: {'OK' if item.get('ok') else 'ERROR'} {item.get('projection_status') or item.get('error')}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Retry or replay webnovel projections from existing commits")
    parser.add_argument("--project-root", required=True)
    sub = parser.add_subparsers(dest="action", required=True)

    retry = sub.add_parser("retry")
    retry.add_argument("--chapter", type=int, required=True)
    retry.add_argument("--format", choices=["json", "text"], default="json")

    replay = sub.add_parser("replay")
    replay.add_argument("--from-chapter", type=int, required=True)
    replay.add_argument("--to-chapter", type=int, required=True)
    replay.add_argument("--format", choices=["json", "text"], default="json")

    args = parser.parse_args()
    if args.action == "retry":
        report = retry_projection(args.project_root, chapter=args.chapter)
        print(format_projection_report(report, args.format))
        raise SystemExit(0 if report.get("ok") else 1)
    report = replay_projections(
        args.project_root,
        start_chapter=args.from_chapter,
        end_chapter=args.to_chapter,
    )
    print(format_projection_report(report, args.format))
    raise SystemExit(0 if report.get("ok") else 1)


if __name__ == "__main__":
    main()
