#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_ensure_scripts_on_path()

from data_modules.chapter_commit_service import ChapterCommitService  # noqa: E402
from data_modules.projection_log import (  # noqa: E402
    _overall_status,
    append_projection_run,
    latest_projection_run,
    projection_log_path,
    projection_run_pending,
    projection_run_failed,
    projection_status_from_run,
    read_projection_runs,
)


def test_projection_log_appends_and_reads_jsonl(tmp_path):
    payload = {
        "meta": {"chapter": 3, "status": "accepted"},
        "projection_status": {"state": "done", "index": "skipped"},
    }

    record = append_projection_run(
        tmp_path,
        payload,
        {"state": {"status": "done"}, "index": {"status": "skipped"}},
    )

    assert projection_log_path(tmp_path).is_file()
    assert record["status"] == "done"
    assert read_projection_runs(tmp_path, chapter=3)[0]["run_id"] == record["run_id"]
    assert latest_projection_run(tmp_path, chapter=3)["commit_hash"] == record["commit_hash"]


def test_projection_status_from_run_prefers_writer_statuses(tmp_path):
    payload = {
        "meta": {"chapter": 3, "status": "accepted"},
        "projection_status": {"state": "done", "vector": "done"},
    }

    record = append_projection_run(
        tmp_path,
        payload,
        {"vector": {"status": "failed:timeout", "error": "timeout"}},
    )

    assert projection_status_from_run(record) == {"vector": "failed:timeout"}
    assert projection_run_failed(record) is True


def test_projection_log_skips_bad_chapter_when_filtering(tmp_path):
    path = projection_log_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                '{"chapter":"bad","writers":{"state":{"status":"done"}}}',
                '{"chapter":3,"writers":{"state":{"status":"done"}}}',
            ]
        ),
        encoding="utf-8",
    )

    records = read_projection_runs(tmp_path, chapter=3)

    assert len(records) == 1
    assert records[0]["chapter"] == 3


def test_projection_run_pending_detects_overall_and_writer_pending():
    assert projection_run_pending({"status": "pending", "writers": {}}) is True
    assert projection_run_pending({"writers": {"state": {"status": "pending"}}}) is True


def test_overall_status_returns_partial_when_any_writer_partial():
    writers = {
        "state": {"status": "done"},
        "vector": {"status": "partial", "partial": True, "stored": 2, "total": 3},
    }
    assert _overall_status(writers) == "partial"


def test_overall_status_prioritizes_failed_over_partial():
    writers = {
        "vector": {"status": "partial", "partial": True},
        "memory": {"status": "failed:timeout"},
    }
    assert _overall_status(writers) == "failed"


def test_overall_status_prioritizes_pending_over_partial():
    writers = {
        "vector": {"status": "partial", "partial": True},
        "memory": {"status": "pending"},
    }
    assert _overall_status(writers) == "pending"


def test_overall_status_returns_done_without_partial():
    writers = {"state": {"status": "done"}, "index": {"status": "done"}}
    assert _overall_status(writers) == "done"


def test_chapter_commit_service_writes_projection_log(tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")

    service = ChapterCommitService(tmp_path)
    payload = service.build_commit(
        chapter=7,
        review_result={"blocking_count": 1},
        fulfillment_result={
            "planned_nodes": ["进入坊市"],
            "covered_nodes": ["进入坊市"],
            "missed_nodes": [],
            "extra_nodes": [],
        },
        disambiguation_result={"pending": []},
        extraction_result={"state_deltas": [], "entity_deltas": [], "accepted_events": []},
    )

    service.apply_projections(payload)

    runs = read_projection_runs(tmp_path, chapter=7)
    assert len(runs) == 1
    assert runs[0]["commit_status"] == "rejected"
    assert runs[0]["writers"]["state"]["status"] == "done"
    assert runs[0]["projection_status"]["state"] == "done"


def test_chapter_commit_service_marks_vector_store_zero_as_failed(monkeypatch, tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "data_modules.vector_projection_writer.VectorProjectionWriter._store_chunks",
        lambda self, chunks: 0,
    )

    service = ChapterCommitService(tmp_path)
    payload = service.build_commit(
        chapter=8,
        review_result={"blocking_count": 0},
        fulfillment_result={
            "planned_nodes": ["突破"],
            "covered_nodes": ["突破"],
            "missed_nodes": [],
            "extra_nodes": [],
        },
        disambiguation_result={"pending": []},
        extraction_result={
            "state_deltas": [],
            "entity_deltas": [],
            "accepted_events": [
                {
                    "event_id": "evt-breakthrough",
                    "event_type": "power_breakthrough",
                    "chapter": 8,
                    "subject": "韩立",
                    "payload": {"field": "realm", "to": "筑基初期"},
                }
            ],
        },
    )

    projected = service.apply_projections(payload)

    assert projected["projection_status"]["vector"] == "failed:store_failed"
    latest = latest_projection_run(tmp_path, chapter=8)
    assert latest is not None
    assert projection_run_failed(latest) is True
    assert latest["writers"]["vector"]["status"] == "failed:store_failed"
