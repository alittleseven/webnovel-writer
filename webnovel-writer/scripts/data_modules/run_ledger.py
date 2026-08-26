#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # pragma: no cover - direct script entry
    scripts_dir = Path(__file__).resolve().parents[1]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

try:
    from chapter_paths import find_chapter_file
except ImportError:  # pragma: no cover
    from scripts.chapter_paths import find_chapter_file

try:
    import long_paths
except ImportError:  # pragma: no cover
    from scripts import long_paths

if __package__ in {None, ""}:  # pragma: no cover - direct script entry
    from data_modules.artifact_validator import OK_PROJECTION_STATUSES, REQUIRED_PROJECTION_WRITERS
    from data_modules.project_phase import COMMIT_ARTIFACT_FILES, contract_files_for_chapter
    from data_modules.projection_log import latest_projection_run, projection_status_from_run
else:
    from .artifact_validator import OK_PROJECTION_STATUSES, REQUIRED_PROJECTION_WRITERS
    from .project_phase import COMMIT_ARTIFACT_FILES, contract_files_for_chapter
    from .projection_log import latest_projection_run, projection_status_from_run


SCHEMA_VERSION = "webnovel-run-ledger/v1"
LEDGER_REL = Path(".webnovel") / "run_ledger.json"
WRITE_STEPS = ("draft", "review", "data", "commit", "projection", "backup")
SUBAGENT_RUN_SCHEMA_VERSION = "webnovel-subagent-run/v1"
SUBAGENT_STATUSES = ("completed", "partial", "failed", "skipped")


def ledger_path(project_root: str | Path) -> Path:
    return Path(project_root) / LEDGER_REL


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_ledger(project_root: str | Path) -> dict[str, Any]:
    payload = _read_json(ledger_path(project_root))
    if payload.get("schema_version") != SCHEMA_VERSION:
        return {"schema_version": SCHEMA_VERSION, "write": {}, "subagent_runs": []}
    payload.setdefault("write", {})
    if not isinstance(payload["write"], dict):
        payload["write"] = {}
    payload.setdefault("subagent_runs", [])
    if not isinstance(payload["subagent_runs"], list):
        payload["subagent_runs"] = []
    return payload


def save_ledger(project_root: str | Path, ledger: dict[str, Any]) -> Path:
    path = ledger_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def file_signature(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not long_paths.is_file(target):
        return {"path": str(target), "exists": False}
    size = long_paths.file_size(target)
    mtime = long_paths.mtime_ns(target)
    digest = hashlib.sha256(long_paths.read_bytes(target)).hexdigest()
    return {
        "path": str(target),
        "exists": True,
        "size": size,
        "mtime_ns": mtime,
        "sha256": digest,
    }


def _chapter_key(chapter: int) -> str:
    return f"chapter_{int(chapter):03d}"


def _write_run(ledger: dict[str, Any], chapter: int, mode: str) -> dict[str, Any]:
    write = ledger.setdefault("write", {})
    key = _chapter_key(chapter)
    run = write.setdefault(key, {})
    run.setdefault("chapter", int(chapter))
    run.setdefault("mode", mode or "default")
    run.setdefault("steps", {})
    run["updated_at"] = _now_iso()
    return run


def record_write_step(
    project_root: str | Path,
    *,
    chapter: int,
    step: str,
    status: str,
    mode: str = "default",
    inputs: dict[str, str | Path] | None = None,
    outputs: dict[str, str | Path] | None = None,
    problems: list[str] | None = None,
    auto_handled: list[str] | None = None,
    duration_ms: int = 0,
) -> dict[str, Any]:
    if step not in WRITE_STEPS:
        raise ValueError(f"unknown write step: {step}")
    root = Path(project_root)
    ledger = load_ledger(root)
    run = _write_run(ledger, chapter, mode)
    input_signatures = {
        str(name): file_signature(path)
        for name, path in (inputs or {}).items()
    }
    output_signatures = {
        str(name): file_signature(path)
        for name, path in (outputs or {}).items()
    }
    entry = {
        "step": step,
        "status": status,
        "recorded_at": _now_iso(),
        "duration_ms": int(duration_ms or 0),
        "inputs": input_signatures,
        "outputs": output_signatures,
        "problems": list(problems or []),
        "auto_handled": list(auto_handled or []),
    }
    run["steps"][step] = entry
    save_ledger(root, ledger)
    return entry


def record_subagent_run(
    project_root: str | Path,
    *,
    run_id: str,
    name: str,
    user_label: str,
    status: str,
    command: str = "",
    stage: str = "",
    chapter: int | None = None,
    volume: int | None = None,
    problems: list[str] | None = None,
    auto_handled: list[str] | None = None,
    needs_user_action: bool = False,
    duration_ms: int = 0,
    outputs: list[str] | None = None,
) -> dict[str, Any]:
    """Persist one author-facing subagent result without changing write-step state."""
    normalized_status = str(status or "").strip()
    if normalized_status not in SUBAGENT_STATUSES:
        raise ValueError(f"unknown subagent status: {normalized_status}")
    if not str(run_id or "").strip():
        raise ValueError("subagent run_id is required")
    if not str(name or "").strip():
        raise ValueError("subagent name is required")

    entry: dict[str, Any] = {
        "schema_version": SUBAGENT_RUN_SCHEMA_VERSION,
        "run_id": str(run_id),
        "name": str(name),
        "user_label": str(user_label or name),
        "status": normalized_status,
        "command": str(command or ""),
        "stage": str(stage or ""),
        "chapter": int(chapter) if chapter is not None else None,
        "volume": int(volume) if volume is not None else None,
        "problems": list(problems or []),
        "auto_handled": list(auto_handled or []),
        "needs_user_action": bool(needs_user_action),
        "duration_ms": max(0, int(duration_ms or 0)),
        "outputs": [str(item) for item in (outputs or [])],
        "recorded_at": _now_iso(),
    }
    try:
        from .run_logger import redact_payload
    except ImportError:  # pragma: no cover - direct script entry
        from data_modules.run_logger import redact_payload
    entry = redact_payload(entry)

    root = Path(project_root)
    ledger = load_ledger(root)
    runs = ledger["subagent_runs"]
    runs[:] = [item for item in runs if not (isinstance(item, dict) and item.get("run_id") == run_id)]
    runs.append(entry)
    save_ledger(root, ledger)
    return entry


def read_subagent_runs(
    project_root: str | Path,
    *,
    command: str | None = None,
    stage: str | None = None,
    chapter: int | None = None,
    latest_only: bool = False,
) -> list[dict[str, Any]]:
    """Read persisted subagent records, optionally scoped to one author workflow."""
    ledger = load_ledger(project_root)
    result: list[dict[str, Any]] = []
    for item in ledger.get("subagent_runs") or []:
        if not isinstance(item, dict):
            continue
        if command is not None and item.get("command") != command:
            continue
        if stage is not None and item.get("stage") != stage:
            continue
        if chapter is not None and item.get("chapter") != int(chapter):
            continue
        result.append(dict(item))
    if not latest_only:
        return result

    latest: dict[str, dict[str, Any]] = {}
    for item in result:
        latest[str(item.get("name") or item.get("run_id"))] = item
    return list(latest.values())


def _same_signature(expected: dict[str, Any] | None, current: dict[str, Any]) -> bool:
    if not isinstance(expected, dict):
        return False
    return bool(expected.get("exists")) and expected.get("sha256") == current.get("sha256")


def _step_completed(run: dict[str, Any], step: str) -> dict[str, Any] | None:
    steps = run.get("steps") if isinstance(run.get("steps"), dict) else {}
    entry = steps.get(step)
    if not isinstance(entry, dict):
        return None
    return entry if entry.get("status") == "completed" else None


def _trusted_output(entry: dict[str, Any] | None, name: str) -> bool:
    if not entry:
        return False
    outputs = entry.get("outputs") if isinstance(entry.get("outputs"), dict) else {}
    expected = outputs.get(name)
    if not isinstance(expected, dict):
        return False
    return _same_signature(expected, file_signature(expected.get("path") or ""))


def _trusted_input(entry: dict[str, Any] | None, name: str, path: Path | None) -> bool:
    if not entry or path is None:
        return False
    inputs = entry.get("inputs") if isinstance(entry.get("inputs"), dict) else {}
    expected = inputs.get(name)
    if not isinstance(expected, dict):
        return False
    return _same_signature(expected, file_signature(path))


def verify_review_chapter_alignment(
    project_root: str | Path,
    chapter: int,
    chapter_file: Path | None,
) -> dict[str, Any] | None:
    """P1-8：校验 precommit 时的正文与 review 步骤记录的正文 sha 是否一致。

    返回 None 表示一致（或无 review 记录可比对，如 --minimal 模式）；
    返回 dict 表示不一致，含 mismatch 详情供 precommit gate 报告。
    """
    if chapter_file is None:
        return None
    root = Path(project_root)
    ledger = load_ledger(root)
    run = ((ledger.get("write") or {}).get(_chapter_key(int(chapter))) or {})
    if not isinstance(run, dict):
        return None
    review_entry = _step_completed(run, "review")
    if review_entry is None:
        # 无 completed 的 review 步骤记录（--minimal 跳过审查等），不阻断
        return None
    if _trusted_input(review_entry, "chapter_file", chapter_file):
        return None
    inputs = review_entry.get("inputs") if isinstance(review_entry.get("inputs"), dict) else {}
    expected = inputs.get("chapter_file") or {}
    return {
        "code": "review_chapter_mismatch",
        "message": "正文与审查记录不一致：审查后正文被修改，当前审查结果可能已失效",
        "expected_sha256": expected.get("sha256") if isinstance(expected, dict) else None,
        "expected_mtime": expected.get("mtime_ns") if isinstance(expected, dict) else None,
        "actual": file_signature(chapter_file),
    }


def _commit_path(project_root: Path, chapter: int) -> Path:
    return project_root / ".story-system" / "commits" / f"chapter_{chapter:03d}.commit.json"


def _commit_status(project_root: Path, chapter: int) -> str:
    payload = _read_json(_commit_path(project_root, chapter))
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    return str(meta.get("status") or "")


def _projection_done(project_root: Path, chapter: int) -> bool:
    run = latest_projection_run(project_root, chapter=chapter)
    statuses = projection_status_from_run(run) if run else {}
    if not statuses:
        payload = _read_json(_commit_path(project_root, chapter))
        raw = payload.get("projection_status") if isinstance(payload.get("projection_status"), dict) else {}
        statuses = {str(key): str(value) for key, value in raw.items()}
    if not statuses:
        return False
    return all(str(statuses.get(writer) or "") in OK_PROJECTION_STATUSES for writer in REQUIRED_PROJECTION_WRITERS)


def _backup_exists(project_root: Path, chapter: int) -> bool:
    backup_dir = project_root / ".webnovel" / "backups"
    if not backup_dir.is_dir():
        return False
    return any(backup_dir.glob(f"ch{chapter:04d}*"))


def _latest_contract_mtime(project_root: Path, chapter: int) -> int:
    mtimes: list[int] = []
    for path in contract_files_for_chapter(project_root, chapter).values():
        if path.is_file():
            mtimes.append(path.stat().st_mtime_ns)
    return max(mtimes or [0])


def build_write_resume_plan(
    project_root: str | Path,
    *,
    chapter: int,
    mode: str = "default",
) -> dict[str, Any]:
    root = Path(project_root)
    ledger = load_ledger(root)
    run = ((ledger.get("write") or {}).get(_chapter_key(chapter)) or {})
    if not isinstance(run, dict):
        run = {}

    chapter_file = find_chapter_file(root, chapter)
    draft_entry = _step_completed(run, "draft")
    review_entry = _step_completed(run, "review")
    data_entry = _step_completed(run, "data")
    commit_status = _commit_status(root, chapter)
    accepted_done = commit_status == "accepted"
    rejected_done = commit_status == "rejected"

    steps: list[dict[str, str]] = []
    confirmations: list[dict[str, str]] = []

    draft_trusted = bool(accepted_done or (chapter_file and _trusted_output(draft_entry, "chapter_file")))
    if draft_entry and chapter_file and not draft_trusted:
        confirmations.append(
            {
                "code": "chapter_file_changed",
                "message": "正文文件与上次记录不一致，需要确认沿用手改正文还是重新起草。",
            }
        )
    if draft_trusted and chapter_file and _latest_contract_mtime(root, chapter) > chapter_file.stat().st_mtime_ns:
        draft_trusted = False
        confirmations.append(
            {
                "code": "outline_newer_than_draft",
                "message": "章纲或合同晚于正文，需要确认沿用旧正文还是重新起草。",
            }
        )
    steps.append({"step": "draft", "action": "skip" if draft_trusted else "run", "reason": "正文可信" if draft_trusted else "正文缺失或已过期"})

    review_path = root / COMMIT_ARTIFACT_FILES[0]
    review_trusted = bool(accepted_done or (draft_trusted and review_path.is_file() and _trusted_input(review_entry, "chapter_file", chapter_file)))
    steps.append({"step": "review", "action": "skip" if review_trusted else "run", "reason": "审查结果匹配当前正文" if review_trusted else "正文变更后需要重审"})

    data_paths = [root / rel for rel in COMMIT_ARTIFACT_FILES[1:]]
    data_trusted = bool(accepted_done or (review_trusted and all(path.is_file() for path in data_paths) and _trusted_input(data_entry, "chapter_file", chapter_file)))
    steps.append({"step": "data", "action": "skip" if data_trusted else "run", "reason": "故事事实提取可信" if data_trusted else "data artifacts 缺失或过期"})

    if accepted_done:
        confirmations.append(
            {
                "code": "chapter_already_accepted",
                "message": "本章已 accepted；重跑前需要确认是重写正文，还是只查看状态/补跑后续步骤。",
            }
        )
    if rejected_done:
        confirmations.append(
            {
                "code": "chapter_commit_rejected",
                "message": "本章事实提交未通过，需要先处理审查/大纲/消歧阻断项，再重新提交。",
            }
        )
    commit_reason = (
        f"commit status={commit_status}"
        if accepted_done
        else "commit rejected，需要修复后重新提交"
        if rejected_done
        else "尚未生成 commit"
    )
    steps.append({"step": "commit", "action": "skip" if accepted_done else "run", "reason": commit_reason})

    projection_done = bool(commit_status == "accepted" and _projection_done(root, chapter))
    projection_action = "skip" if projection_done else ("retry" if accepted_done else "run")
    projection_reason = (
        "资料更新已完成"
        if projection_done
        else "commit accepted 后再更新资料"
        if not accepted_done
        else "需要补跑资料更新"
    )
    steps.append({"step": "projection", "action": projection_action, "reason": projection_reason})

    backup_done = _backup_exists(root, chapter)
    backup_action = "skip" if backup_done else ("retry" if commit_status == "accepted" else "run")
    steps.append({"step": "backup", "action": backup_action, "reason": "备份已确认" if backup_done else "备份未确认"})

    resume_from = "done"
    for item in steps:
        if item["action"] != "skip":
            resume_from = item["step"]
            break

    return {
        "schema_version": SCHEMA_VERSION,
        "stage": "write",
        "chapter": int(chapter),
        "mode": mode or "default",
        "resume_from": resume_from,
        "steps": steps,
        "needs_user_confirmation": confirmations,
    }


def format_resume_plan(plan: dict[str, Any], output_format: str = "json") -> str:
    if output_format == "json":
        return json.dumps(plan, ensure_ascii=False, indent=2)
    lines = [
        f"resume_from: {plan.get('resume_from')}",
        f"chapter: {plan.get('chapter')}",
    ]
    for item in plan.get("steps") or []:
        lines.append(f"- {item.get('step')}: {item.get('action')} ({item.get('reason')})")
    confirmations = plan.get("needs_user_confirmation") or []
    if confirmations:
        lines.append("needs_user_confirmation:")
        lines.extend(f"- {item.get('code')}: {item.get('message')}" for item in confirmations)
    return "\n".join(lines)


def _parse_path_map(raw: str) -> dict[str, str]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"不是合法 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("必须是 JSON object")
    return {str(key): str(value) for key, value in payload.items()}


def _parse_string_list(raw: str) -> list[str]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"不是合法 JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("必须是 JSON list")
    return [str(item) for item in payload]


def main() -> None:
    parser = argparse.ArgumentParser(description="Record and inspect webnovel write run ledger")
    parser.add_argument("--project-root", required=True, help="书项目根目录")
    sub = parser.add_subparsers(dest="action", required=True)
    record = sub.add_parser("record-write-step", help="记录写章步骤状态")
    record.add_argument("--chapter", type=int, required=True)
    record.add_argument("--step", choices=WRITE_STEPS, required=True)
    record.add_argument("--status", required=True)
    record.add_argument("--mode", default="default")
    record.add_argument("--inputs-json", default="{}")
    record.add_argument("--outputs-json", default="{}")
    record.add_argument("--problems-json", default="[]")
    record.add_argument("--auto-handled-json", default="[]")
    record.add_argument("--duration-ms", type=int, default=0)
    record.add_argument("--format", choices=["json", "text"], default="json")
    resume = sub.add_parser("write-resume", help="输出写章断点续跑建议")
    resume.add_argument("--chapter", type=int, required=True)
    resume.add_argument("--mode", default="default")
    resume.add_argument("--format", choices=["json", "text"], default="json")
    args = parser.parse_args()

    if args.action == "record-write-step":
        try:
            entry = record_write_step(
                args.project_root,
                chapter=args.chapter,
                step=args.step,
                status=args.status,
                mode=args.mode,
                inputs=_parse_path_map(args.inputs_json),
                outputs=_parse_path_map(args.outputs_json),
                problems=_parse_string_list(args.problems_json),
                auto_handled=_parse_string_list(args.auto_handled_json),
                duration_ms=args.duration_ms,
            )
        except ValueError as exc:
            raise SystemExit(str(exc))
        if args.format == "json":
            print(json.dumps(entry, ensure_ascii=False, indent=2))
        else:
            print(f"{entry['step']}: {entry['status']}")
        return

    if args.action == "write-resume":
        plan = build_write_resume_plan(args.project_root, chapter=args.chapter, mode=args.mode)
        print(format_resume_plan(plan, args.format))


if __name__ == "__main__":
    main()
