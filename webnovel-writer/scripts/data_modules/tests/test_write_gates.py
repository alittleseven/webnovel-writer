#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
from pathlib import Path

from .test_project_phase import _make_contracts, _make_init_ready, _write_json


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_ensure_scripts_on_path()

from data_modules.write_gates import run_write_gate  # noqa: E402
from data_modules.projection_log import append_projection_run  # noqa: E402


def _write_valid_artifacts(project_root: Path) -> None:
    _write_json(project_root / ".webnovel" / "tmp" / "review_results.json", {"blocking_count": 0})
    _write_json(
        project_root / ".webnovel" / "tmp" / "fulfillment_result.json",
        {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
    )
    _write_json(project_root / ".webnovel" / "tmp" / "disambiguation_result.json", {"pending": []})
    _write_json(
        project_root / ".webnovel" / "tmp" / "extraction_result.json",
        {"accepted_events": [], "state_deltas": [], "entity_deltas": [], "summary_text": "摘要"},
    )


def test_prewrite_gate_allows_contract_ready_project_with_warning(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)

    report = run_write_gate(tmp_path, chapter=1, stage="prewrite")

    assert report["ok"] is True
    assert report["stage"] == "prewrite"
    assert report["details"]["prewrite_validation"]["blocking"] is False


def test_prewrite_gate_wraps_existing_prewrite_validator_blocking(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    state_path = tmp_path / ".webnovel" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["disambiguation_pending"] = [{"mention": "宗主"}]
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    report = run_write_gate(tmp_path, chapter=1, stage="prewrite")

    assert report["ok"] is False
    assert any(item["code"] == "prewrite_validator_blocking" for item in report["errors"])
    assert report["details"]["prewrite_validation"]["disambiguation_domain"]["pending_count"] == 1


def test_precommit_gate_reports_missing_artifacts(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    (tmp_path / "正文" / "第0001章.md").write_text("正文\n", encoding="utf-8")

    report = run_write_gate(tmp_path, chapter=1, stage="precommit")

    assert report["ok"] is False
    assert any(item["code"] == "artifact.missing_artifact" for item in report["errors"])


def test_precommit_gate_accepts_valid_artifacts(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    (tmp_path / "正文" / "第0001章.md").write_text("正文\n", encoding="utf-8")
    _write_valid_artifacts(tmp_path)

    report = run_write_gate(tmp_path, chapter=1, stage="precommit")

    assert report["ok"] is True
    assert report["details"]["artifact_report"]["ok"] is True


def test_precommit_gate_rejects_fulfillment_missing_missed_nodes(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    (tmp_path / "正文" / "第0001章.md").write_text("正文\n", encoding="utf-8")
    _write_valid_artifacts(tmp_path)
    _write_json(
        tmp_path / ".webnovel" / "tmp" / "fulfillment_result.json",
        {"planned_nodes": [], "covered_nodes": [], "extra_nodes": []},
    )

    report = run_write_gate(tmp_path, chapter=1, stage="precommit")

    assert report["ok"] is False
    assert any(item["code"] == "artifact.schema_error" for item in report["errors"])
    assert any("missed_nodes" in item["message"] for item in report["errors"])


def test_precommit_gate_rejects_disambiguation_missing_pending(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    (tmp_path / "正文" / "第0001章.md").write_text("正文\n", encoding="utf-8")
    _write_valid_artifacts(tmp_path)
    _write_json(tmp_path / ".webnovel" / "tmp" / "disambiguation_result.json", {"warnings": []})

    report = run_write_gate(tmp_path, chapter=1, stage="precommit")

    assert report["ok"] is False
    assert any(item["code"] == "artifact.schema_error" for item in report["errors"])
    assert any("pending" in item["message"] for item in report["errors"])


def test_precommit_gate_rejects_extraction_missing_accepted_events(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    (tmp_path / "正文" / "第0001章.md").write_text("正文\n", encoding="utf-8")
    _write_valid_artifacts(tmp_path)
    _write_json(
        tmp_path / ".webnovel" / "tmp" / "extraction_result.json",
        {"state_deltas": [], "entity_deltas": [], "summary_text": "摘要"},
    )

    report = run_write_gate(tmp_path, chapter=1, stage="precommit")

    assert report["ok"] is False
    assert any(item["code"] == "artifact.schema_error" for item in report["errors"])
    assert any("accepted_events" in item["message"] for item in report["errors"])


def test_precommit_gate_blocks_projection_failed_phase(tmp_path):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    (tmp_path / "正文" / "第0001章.md").write_text("正文\n", encoding="utf-8")
    _write_valid_artifacts(tmp_path)
    _write_json(
        tmp_path / ".story-system" / "commits" / "chapter_001.commit.json",
        {
            "meta": {"chapter": 1, "status": "accepted"},
            "projection_status": {"state": "done", "index": "failed:locked"},
        },
    )

    report = run_write_gate(tmp_path, chapter=1, stage="precommit")

    assert report["ok"] is False
    assert any(item["code"] == "phase_not_ready_for_precommit" for item in report["errors"])


def test_postcommit_gate_reports_projection_failure(tmp_path):
    _make_init_ready(tmp_path)
    _write_json(
        tmp_path / ".story-system" / "commits" / "chapter_001.commit.json",
        {
            "meta": {"chapter": 1, "status": "accepted"},
            "review_result": {"blocking_count": 0},
            "fulfillment_result": {
                "planned_nodes": [],
                "covered_nodes": [],
                "missed_nodes": [],
                "extra_nodes": [],
            },
            "disambiguation_result": {"pending": []},
            "extraction_result": {
                "accepted_events": [],
                "state_deltas": [],
                "entity_deltas": [],
                "summary_text": "摘要",
            },
            "projection_status": {"state": "done", "index": "failed:locked", "summary": "skipped"},
        },
    )

    report = run_write_gate(tmp_path, chapter=1, stage="postcommit")

    assert report["ok"] is False
    assert any(item["code"] == "commit.projection_failure" for item in report["errors"])


def test_postcommit_gate_prefers_projection_log_failure(tmp_path):
    _make_init_ready(tmp_path)
    commit_payload = {
        "meta": {"chapter": 1, "status": "accepted"},
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {
            "planned_nodes": [],
            "covered_nodes": [],
            "missed_nodes": [],
            "extra_nodes": [],
        },
        "disambiguation_result": {"pending": []},
        "extraction_result": {
            "accepted_events": [],
            "state_deltas": [],
            "entity_deltas": [],
            "summary_text": "摘要",
        },
        "projection_status": {"state": "done", "index": "done", "vector": "done"},
    }
    commit_path = tmp_path / ".story-system" / "commits" / "chapter_001.commit.json"
    _write_json(commit_path, commit_payload)
    append_projection_run(
        tmp_path,
        commit_payload,
        {"vector": {"status": "failed:timeout", "error": "timeout"}},
        commit_path=commit_path,
    )

    report = run_write_gate(tmp_path, chapter=1, stage="postcommit")

    assert report["ok"] is False
    assert any(item["code"] == "projection_failure" for item in report["errors"])
    assert report["details"]["projection_source"] == "projection_log"


def test_postcommit_gate_requires_five_projection_statuses_from_projection_log(tmp_path):
    _make_init_ready(tmp_path)
    commit_payload = {
        "meta": {"chapter": 1, "status": "accepted"},
        "review_result": {"blocking_count": 0},
        "fulfillment_result": {
            "planned_nodes": [],
            "covered_nodes": [],
            "missed_nodes": [],
            "extra_nodes": [],
        },
        "disambiguation_result": {"pending": []},
        "extraction_result": {
            "accepted_events": [],
            "state_deltas": [],
            "entity_deltas": [],
            "summary_text": "摘要",
        },
        "projection_status": {
            "state": "done",
            "index": "done",
            "summary": "skipped",
            "memory": "skipped",
            "vector": "done",
        },
    }
    commit_path = tmp_path / ".story-system" / "commits" / "chapter_001.commit.json"
    _write_json(commit_path, commit_payload)
    append_projection_run(
        tmp_path,
        commit_payload,
        {"vector": {"status": "done"}},
        commit_path=commit_path,
    )

    report = run_write_gate(tmp_path, chapter=1, stage="postcommit")

    assert report["ok"] is False
    assert report["details"]["projection_source"] == "projection_log"
    assert any(item["code"] == "projection_status_missing" for item in report["errors"])
    assert any("state" in item["message"] for item in report["errors"])


def test_postcommit_gate_accepts_done_or_skipped_projection(tmp_path):
    _make_init_ready(tmp_path)
    _write_json(
        tmp_path / ".story-system" / "commits" / "chapter_001.commit.json",
        {
            "meta": {"chapter": 1, "status": "accepted"},
            "review_result": {"blocking_count": 0},
            "fulfillment_result": {
                "planned_nodes": [],
                "covered_nodes": [],
                "missed_nodes": [],
                "extra_nodes": [],
            },
            "disambiguation_result": {"pending": []},
            "extraction_result": {
                "accepted_events": [],
                "state_deltas": [],
                "entity_deltas": [],
                "summary_text": "摘要",
            },
            "projection_status": {
                "state": "done",
                "index": "skipped",
                "summary": "skipped",
                "memory": "skipped",
                "vector": "skipped",
            },
        },
    )

    report = run_write_gate(tmp_path, chapter=1, stage="postcommit")

    assert report["ok"] is True


def test_precommit_gate_blocks_when_chapter_changed_after_review(tmp_path):
    """P1-8：审查后正文被修改 → precommit 阻止提交（防止旧审查配新正文）。"""
    from data_modules.run_ledger import record_write_step

    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    chapter_file = tmp_path / "正文" / "第0001章.md"
    chapter_file.write_text("原始正文\n", encoding="utf-8")
    _write_valid_artifacts(tmp_path)

    # 记录 review 步骤（inputs 含 chapter_file 签名）
    record_write_step(
        tmp_path,
        chapter=1,
        step="review",
        status="completed",
        inputs={"chapter_file": chapter_file},
    )

    # 审查后修改正文
    chapter_file.write_text("修改后的正文\n", encoding="utf-8")

    report = run_write_gate(tmp_path, chapter=1, stage="precommit")

    assert report["ok"] is False
    assert any(item["code"] == "review_chapter_mismatch" for item in report["errors"])


def test_precommit_gate_passes_when_chapter_unchanged_after_review(tmp_path):
    """P1-8：正文与 review 记录一致 → precommit 不报 mismatch。"""
    from data_modules.run_ledger import record_write_step

    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    chapter_file = tmp_path / "正文" / "第0001章.md"
    chapter_file.write_text("正文内容\n", encoding="utf-8")
    _write_valid_artifacts(tmp_path)

    record_write_step(
        tmp_path,
        chapter=1,
        step="review",
        status="completed",
        inputs={"chapter_file": chapter_file},
    )

    report = run_write_gate(tmp_path, chapter=1, stage="precommit")

    # 不应出现 review_chapter_mismatch 错误
    assert not any(item["code"] == "review_chapter_mismatch" for item in report.get("errors", []))
