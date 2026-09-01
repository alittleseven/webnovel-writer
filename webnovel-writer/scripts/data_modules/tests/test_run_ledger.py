#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from pathlib import Path


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_ensure_scripts_on_path()

from data_modules.run_ledger import (  # noqa: E402
    build_write_resume_plan,
    read_subagent_runs,
    record_subagent_run,
    record_write_step,
    verify_review_chapter_alignment,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_project(project_root: Path) -> None:
    (project_root / ".webnovel" / "tmp").mkdir(parents=True, exist_ok=True)
    (project_root / ".story-system" / "commits").mkdir(parents=True, exist_ok=True)
    (project_root / "正文").mkdir(parents=True, exist_ok=True)
    _write_json(project_root / ".webnovel" / "state.json", {"project_info": {"title": "测试书"}, "progress": {}})


def _commit_payload(status: str = "accepted") -> dict:
    return {
        "meta": {"chapter": 1, "status": status},
        "projection_status": {
            "state": "done",
            "index": "skipped",
            "summary": "skipped",
            "memory": "skipped",
            "vector": "skipped",
        },
    }


def test_run_ledger_records_write_step_status(tmp_path: Path) -> None:
    _make_project(tmp_path)
    chapter_file = tmp_path / "正文" / "第0001章.md"
    chapter_file.write_text("正文\n", encoding="utf-8")

    entry = record_write_step(
        tmp_path,
        chapter=1,
        step="draft",
        status="completed",
        outputs={"chapter_file": chapter_file},
    )

    assert entry["status"] == "completed"
    assert entry["outputs"]["chapter_file"]["exists"] is True
    assert (tmp_path / ".webnovel" / "run_ledger.json").is_file()


def test_run_ledger_records_and_reads_subagent_run_with_redaction(tmp_path: Path) -> None:
    _make_project(tmp_path)

    entry = record_subagent_run(
        tmp_path,
        run_id="write-0001-context-1",
        name="context-agent",
        user_label="整理写作依据",
        status="partial",
        command="webnovel-write",
        stage="write",
        chapter=1,
        problems=["EMBED_API_KEY=secret-value"],
        auto_handled=["使用关键词检索"],
        needs_user_action=True,
        duration_ms=1250,
        outputs=["写作任务书"],
    )

    assert entry["schema_version"] == "webnovel-subagent-run/v1"
    assert entry["status"] == "partial"
    assert entry["problems"] == ["EMBED_API_KEY=<redacted>"]
    assert read_subagent_runs(tmp_path, stage="write", chapter=1) == [entry]

    ledger = json.loads((tmp_path / ".webnovel" / "run_ledger.json").read_text(encoding="utf-8"))
    assert ledger["subagent_runs"][0]["run_id"] == "write-0001-context-1"


def test_run_ledger_rejects_unknown_subagent_status(tmp_path: Path) -> None:
    _make_project(tmp_path)

    try:
        record_subagent_run(
            tmp_path,
            run_id="run-1",
            name="reviewer",
            user_label="写作检查",
            status="unknown",
        )
    except ValueError as exc:
        assert "unknown subagent status" in str(exc)
    else:
        raise AssertionError("unknown subagent status must be rejected")


def test_write_resume_skips_completed_draft_and_review(tmp_path: Path) -> None:
    _make_project(tmp_path)
    chapter_file = tmp_path / "正文" / "第0001章.md"
    chapter_file.write_text("正文\n", encoding="utf-8")
    review_path = tmp_path / ".webnovel" / "tmp" / "review_results.json"
    _write_json(review_path, {"blocking_count": 0})

    record_write_step(tmp_path, chapter=1, step="draft", status="completed", outputs={"chapter_file": chapter_file})
    record_write_step(
        tmp_path,
        chapter=1,
        step="review",
        status="completed",
        inputs={"chapter_file": chapter_file},
        outputs={"review_result": review_path},
    )

    plan = build_write_resume_plan(tmp_path, chapter=1)

    actions = {item["step"]: item["action"] for item in plan["steps"]}
    assert actions["draft"] == "skip"
    assert actions["review"] == "skip"
    assert actions["data"] == "run"


def test_write_resume_rechecks_review_when_chapter_file_changed(tmp_path: Path) -> None:
    _make_project(tmp_path)
    chapter_file = tmp_path / "正文" / "第0001章.md"
    chapter_file.write_text("正文 v1\n", encoding="utf-8")
    record_write_step(tmp_path, chapter=1, step="draft", status="completed", outputs={"chapter_file": chapter_file})
    chapter_file.write_text("正文 v2\n", encoding="utf-8")

    plan = build_write_resume_plan(tmp_path, chapter=1)

    actions = {item["step"]: item["action"] for item in plan["steps"]}
    assert actions["draft"] == "run"
    assert actions["review"] == "run"
    assert any(item["code"] == "chapter_file_changed" for item in plan["needs_user_confirmation"])


def test_write_resume_retries_backup_after_commit_done(tmp_path: Path) -> None:
    _make_project(tmp_path)
    chapter_file = tmp_path / "正文" / "第0001章.md"
    chapter_file.write_text("正文\n", encoding="utf-8")
    record_write_step(tmp_path, chapter=1, step="draft", status="completed", outputs={"chapter_file": chapter_file})
    _write_json(tmp_path / ".story-system" / "commits" / "chapter_001.commit.json", _commit_payload("accepted"))

    plan = build_write_resume_plan(tmp_path, chapter=1)

    actions = {item["step"]: item["action"] for item in plan["steps"]}
    assert actions["draft"] == "skip"
    assert actions["review"] == "skip"
    assert actions["data"] == "skip"
    assert actions["commit"] == "skip"
    assert actions["projection"] == "skip"
    assert actions["backup"] == "retry"
    assert plan["resume_from"] == "backup"
    assert any(item["code"] == "chapter_already_accepted" for item in plan["needs_user_confirmation"])


def test_write_resume_reruns_commit_after_rejected_commit(tmp_path: Path) -> None:
    _make_project(tmp_path)
    chapter_file = tmp_path / "正文" / "第0001章.md"
    chapter_file.write_text("正文\n", encoding="utf-8")
    review_path = tmp_path / ".webnovel" / "tmp" / "review_results.json"
    _write_json(review_path, {"blocking_count": 1})
    fulfillment_path = tmp_path / ".webnovel" / "tmp" / "fulfillment_result.json"
    disambiguation_path = tmp_path / ".webnovel" / "tmp" / "disambiguation_result.json"
    extraction_path = tmp_path / ".webnovel" / "tmp" / "extraction_result.json"
    _write_json(fulfillment_path, {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []})
    _write_json(disambiguation_path, {"pending": []})
    _write_json(extraction_path, {"accepted_events": [], "state_deltas": [], "entity_deltas": []})
    record_write_step(
        tmp_path,
        chapter=1,
        step="draft",
        status="completed",
        outputs={"chapter_file": chapter_file},
    )
    record_write_step(
        tmp_path,
        chapter=1,
        step="review",
        status="completed",
        inputs={"chapter_file": chapter_file},
        outputs={"review_result": review_path},
    )
    record_write_step(
        tmp_path,
        chapter=1,
        step="data",
        status="completed",
        inputs={"chapter_file": chapter_file},
        outputs={
            "fulfillment_result": fulfillment_path,
            "disambiguation_result": disambiguation_path,
            "extraction_result": extraction_path,
        },
    )
    _write_json(tmp_path / ".story-system" / "commits" / "chapter_001.commit.json", _commit_payload("rejected"))

    plan = build_write_resume_plan(tmp_path, chapter=1)

    actions = {item["step"]: item["action"] for item in plan["steps"]}
    assert actions["commit"] == "run"
    assert actions["projection"] == "run"
    assert plan["resume_from"] == "commit"
    assert any(item["code"] == "chapter_commit_rejected" for item in plan["needs_user_confirmation"])


def test_verify_review_chapter_alignment_returns_none_when_consistent(tmp_path: Path) -> None:
    """P1-8：正文与 review 记录一致 → None（不阻断）。"""
    _make_project(tmp_path)
    chapter_file = tmp_path / "正文" / "第0001章.md"
    chapter_file.write_text("正文内容\n", encoding="utf-8")

    record_write_step(
        tmp_path,
        chapter=1,
        step="review",
        status="completed",
        inputs={"chapter_file": chapter_file},
    )

    assert verify_review_chapter_alignment(tmp_path, 1, chapter_file) is None


def test_verify_review_chapter_alignment_detects_mismatch(tmp_path: Path) -> None:
    """P1-8：审查后正文被修改 → 返回 mismatch 详情。"""
    _make_project(tmp_path)
    chapter_file = tmp_path / "正文" / "第0001章.md"
    chapter_file.write_text("原始正文\n", encoding="utf-8")

    record_write_step(
        tmp_path,
        chapter=1,
        step="review",
        status="completed",
        inputs={"chapter_file": chapter_file},
    )

    # 审查后修改正文
    chapter_file.write_text("修改后的正文\n", encoding="utf-8")

    result = verify_review_chapter_alignment(tmp_path, 1, chapter_file)
    assert result is not None
    assert result["code"] == "review_chapter_mismatch"
    assert result["expected_sha256"] != result["actual"]["sha256"]


def test_verify_review_chapter_alignment_skips_without_review_record(tmp_path: Path) -> None:
    """P1-8：无 review 步骤记录（--minimal 等）→ None（不阻断）。"""
    _make_project(tmp_path)
    chapter_file = tmp_path / "正文" / "第0001章.md"
    chapter_file.write_text("正文\n", encoding="utf-8")

    assert verify_review_chapter_alignment(tmp_path, 1, chapter_file) is None


def test_verify_review_chapter_alignment_skips_when_review_not_completed(tmp_path: Path) -> None:
    """P1-8：review 步骤未完成 → None（不阻断）。"""
    _make_project(tmp_path)
    chapter_file = tmp_path / "正文" / "第0001章.md"
    chapter_file.write_text("正文\n", encoding="utf-8")

    record_write_step(
        tmp_path,
        chapter=1,
        step="review",
        status="failed",
        inputs={"chapter_file": chapter_file},
    )

    assert verify_review_chapter_alignment(tmp_path, 1, chapter_file) is None


def test_record_write_step_waits_for_external_lock(tmp_path):
    """增量审阅 P3-20：台账读-改-写必须持锁——外部持锁时记账阻塞，释放后完成。"""
    import threading

    import filelock

    from data_modules.run_ledger import ledger_path, record_write_step

    lock = filelock.FileLock(str(ledger_path(tmp_path)) + ".lock", timeout=30)
    result: dict = {}
    with lock:
        thread = threading.Thread(
            target=lambda: result.update(
                entry=record_write_step(tmp_path, chapter=1, step="draft", status="completed")
            )
        )
        thread.start()
        thread.join(timeout=0.5)
        assert thread.is_alive(), "记账未等待台账锁"
        assert not ledger_path(tmp_path).exists(), "持锁期间台账被写出"

    thread.join(timeout=10)
    assert "entry" in result
    assert ledger_path(tmp_path).exists()


def test_concurrent_record_steps_all_persist(tmp_path):
    """增量审阅 P3-20：并发记账不得互相覆盖（锁内 RMW）。"""
    import concurrent.futures

    from data_modules.run_ledger import WRITE_STEPS, load_ledger, record_write_step

    (tmp_path / "正文").mkdir()
    (tmp_path / "正文" / "第0001章.md").write_text("正文", encoding="utf-8")

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [
            pool.submit(record_write_step, tmp_path, chapter=1, step=step, status="completed")
            for step in WRITE_STEPS
        ]
        for future in futures:
            future.result()

    steps = load_ledger(tmp_path)["write"]["chapter_001"]["steps"]
    assert set(steps) == set(WRITE_STEPS)
