#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path

from .test_project_phase import _make_contracts, _make_init_ready
from .test_project_phase import _write_json


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_ensure_scripts_on_path()

import data_modules.doctor as doctor_module  # noqa: E402
from data_modules.projection_log import append_projection_run  # noqa: E402


def test_doctor_init_ready_does_not_require_story_contracts(tmp_path, monkeypatch):
    _make_init_ready(tmp_path)
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    assert report["ok"] is True
    assert report["phase"] == "init_ready"
    assert not [item for item in report["checks"] if str(item["id"]).startswith("file.contract.")]


def test_doctor_missing_init_file_blocks_with_repair(tmp_path, monkeypatch):
    _make_init_ready(tmp_path)
    (tmp_path / "大纲" / "总纲.md").unlink()
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    assert report["ok"] is False
    matches = [item for item in report["checks"] if item["id"] == "file.required.大纲/总纲.md"]
    assert matches
    assert matches[0]["status"] == "error"
    assert matches[0]["repair"]


def test_doctor_checks_contracts_after_story_system_starts(tmp_path, monkeypatch):
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    (tmp_path / ".story-system" / "reviews" / "chapter_001.review.json").unlink()
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    assert report["ok"] is False
    contract_checks = [item for item in report["checks"] if item["id"] == "file.contract.review"]
    assert contract_checks
    assert contract_checks[0]["status"] == "error"


def test_doctor_no_project_reports_repair(monkeypatch):
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(None)

    assert report["ok"] is False
    assert report["phase"] == "no_project"
    assert report["recommended_actions"]


def test_doctor_warns_when_old_project_has_commit_without_projection_log(tmp_path, monkeypatch):
    _make_init_ready(tmp_path)
    _write_json(
        tmp_path / ".story-system" / "commits" / "chapter_001.commit.json",
        {
            "meta": {"chapter": 1, "status": "accepted"},
            "projection_status": {"state": "done"},
        },
    )
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    assert report["ok"] is True
    matches = [item for item in report["checks"] if item["id"] == "projection_log.present"]
    assert matches
    assert matches[0]["status"] == "warning"


def test_doctor_blocks_pending_projection_log_run(tmp_path, monkeypatch):
    _make_init_ready(tmp_path)
    commit_payload = {
        "meta": {"chapter": 1, "status": "accepted"},
        "projection_status": {"state": "pending"},
    }
    commit_path = tmp_path / ".story-system" / "commits" / "chapter_001.commit.json"
    _write_json(commit_path, commit_payload)
    append_projection_run(
        tmp_path,
        commit_payload,
        {"state": {"status": "pending"}},
        commit_path=commit_path,
    )
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    matches = [item for item in report["checks"] if item["id"] == "projection_log.latest_run"]
    assert matches
    assert matches[0]["status"] == "error"
    assert report["ok"] is False


def test_doctor_flags_extraction_warnings_in_accepted_commit(tmp_path, monkeypatch):
    _make_init_ready(tmp_path)
    _write_json(
        tmp_path / ".story-system" / "commits" / "chapter_001.commit.json",
        {
            "meta": {
                "chapter": 1,
                "status": "accepted",
                "extraction_warnings": [
                    {"code": "event_chapter_unparseable", "event_id": "evt-1"},
                ],
            },
            "projection_status": {"state": "done"},
        },
    )
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    matches = [item for item in report["checks"] if item["id"] == "commit.extraction_warnings"]
    assert matches
    assert matches[0]["status"] == "warning"
    assert "event_chapter_unparseable" in matches[0]["actual"]


def test_doctor_ok_when_no_extraction_warnings(tmp_path, monkeypatch):
    _make_init_ready(tmp_path)
    _write_json(
        tmp_path / ".story-system" / "commits" / "chapter_001.commit.json",
        {
            "meta": {"chapter": 1, "status": "accepted", "extraction_warnings": []},
            "projection_status": {"state": "done"},
        },
    )
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    matches = [item for item in report["checks"] if item["id"] == "commit.extraction_warnings"]
    assert matches
    assert matches[0]["status"] == "ok"


def test_doctor_skips_extraction_check_without_accepted_commit(tmp_path, monkeypatch):
    _make_init_ready(tmp_path)
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    matches = [item for item in report["checks"] if item["id"] == "commit.extraction_warnings"]
    assert matches
    assert matches[0]["status"] == "skipped"


def test_doctor_master_setting_missing_blocks_when_chapters_exist(tmp_path, monkeypatch):
    """P1-7：已写多章但 MASTER_SETTING 缺失 → error（不再是 SKIPPED）。"""
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    # 模拟已写多章
    state_path = tmp_path / ".webnovel" / "state.json"
    import json
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["progress"] = {"current_chapter": 5}
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    # 删除 MASTER_SETTING
    master_path = tmp_path / ".story-system" / "MASTER_SETTING.json"
    if master_path.exists():
        master_path.unlink()
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    matches = [
        item for item in report["checks"]
        if "MASTER_SETTING" in str(item.get("id") or "")
    ]
    assert matches
    assert matches[0]["status"] == "error"
    assert matches[0]["severity"] == "blocker"


def test_doctor_master_setting_missing_skipped_when_no_chapters(tmp_path, monkeypatch):
    """P1-7：无正文时 MASTER_SETTING 缺失仍为 SKIPPED（init 阶段正常）。"""
    _make_init_ready(tmp_path)
    # _make_init_ready 不创建 MASTER_SETTING，本来就不存在
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    matches = [
        item for item in report["checks"]
        if "MASTER_SETTING" in str(item.get("id") or "")
    ]
    assert matches
    assert matches[0]["status"] == "skipped"


def test_doctor_flags_broken_contract_json(tmp_path, monkeypatch):
    """P1-7：合同 JSON 损坏 → error。"""
    _make_init_ready(tmp_path)
    _make_contracts(tmp_path, chapter=1)
    # 写一个损坏的 chapter 合同
    chapter_dir = tmp_path / ".story-system" / "chapters"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    (chapter_dir / "chapter_002.json").write_text("{broken json", encoding="utf-8")
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    matches = [item for item in report["checks"] if item["id"] == "json.contracts.chapters"]
    assert matches
    assert matches[0]["status"] == "error"


def test_doctor_run_log_warns_when_only_write_start(tmp_path, monkeypatch):
    """P1-6 诊断：run_last.log 只有 write-start → warning。"""
    _make_init_ready(tmp_path)
    log_dir = tmp_path / ".webnovel" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "run_last.log").write_text(
        '[2026-08-23] event=write-start chapter=1\n', encoding="utf-8"
    )
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    matches = [item for item in report["checks"] if item["id"] == "run_log.step_coverage"]
    assert matches
    assert matches[0]["status"] == "warning"


def test_doctor_run_log_ok_when_step_logs_present(tmp_path, monkeypatch):
    """P1-6 诊断：run_last.log 含关键步骤日志 → ok。"""
    _make_init_ready(tmp_path)
    log_dir = tmp_path / ".webnovel" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "run_last.log").write_text(
        '[2026-08-23] event=write-start chapter=1\n'
        '[2026-08-23] event=step-draft chapter=1 status=completed\n'
        '[2026-08-23] event=step-review chapter=1 status=completed\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])

    report = doctor_module.build_doctor_report(tmp_path)

    matches = [item for item in report["checks"] if item["id"] == "run_log.step_coverage"]
    assert matches
    assert matches[0]["status"] == "ok"


def test_sqlite_null_embedding_count_counts_null_rows(tmp_path):
    """P1-9：vectors 表 embedding 为 NULL 的行应被统计（语义检索缺失告警）。"""
    import sqlite3

    db_path = tmp_path / "vectors.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE vectors (chunk_id TEXT PRIMARY KEY, embedding BLOB, content TEXT)"
    )
    conn.execute(
        "INSERT INTO vectors (chunk_id, embedding, content) VALUES ('a', NULL, '仅BM25')"
    )
    conn.execute(
        "INSERT INTO vectors (chunk_id, embedding, content) VALUES ('b', x'0102', '有向量')"
    )
    conn.commit()
    conn.close()

    assert doctor_module._sqlite_null_embedding_count(db_path) == 1


def test_sqlite_null_embedding_count_returns_none_when_table_missing(tmp_path):
    import sqlite3

    db_path = tmp_path / "vectors.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE other (id INTEGER)")
    conn.commit()
    conn.close()

    assert doctor_module._sqlite_null_embedding_count(db_path) is None


def _write_state_total_words(project_root: Path, total_words: int) -> None:
    import json

    state_path = project_root / ".webnovel" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.setdefault("progress", {})["total_words"] = total_words
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _write_index_chapter_words(project_root: Path, word_count: int) -> None:
    import sqlite3

    conn = sqlite3.connect(str(project_root / ".webnovel" / "index.db"))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS chapters (chapter INTEGER PRIMARY KEY, word_count INTEGER,"
        " title TEXT, summary TEXT, file_path TEXT)"
    )
    conn.execute("INSERT OR REPLACE INTO chapters (chapter, word_count) VALUES (1, ?)", (word_count,))
    conn.commit()
    conn.close()


def test_doctor_warns_on_total_words_reconcile_mismatch(tmp_path, monkeypatch):
    """增量审阅 P2-8：state.total_words 与 index SUM(word_count) 漂移超阈值时 doctor 亮警告。"""
    import sqlite3  # noqa: F401

    _make_init_ready(tmp_path)
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])
    _write_state_total_words(tmp_path, 1000)
    _write_index_chapter_words(tmp_path, 9000)

    report = doctor_module.build_doctor_report(tmp_path)

    mismatches = [
        item for item in report["checks"]
        if item["id"] == "state.total_words_reconcile" and item["status"] == doctor_module.CHECK_WARNING
    ]
    assert mismatches, "总字数对账漂移未被发现"
    assert "1000" in mismatches[0]["actual"] and "9000" in mismatches[0]["actual"]


def test_doctor_total_words_reconcile_within_tolerance_passes(tmp_path, monkeypatch):
    _make_init_ready(tmp_path)
    monkeypatch.setattr(doctor_module, "_python_checks", lambda: [])
    _write_state_total_words(tmp_path, 5000)
    _write_index_chapter_words(tmp_path, 5100)

    report = doctor_module.build_doctor_report(tmp_path)

    assert not [
        item for item in report["checks"]
        if item["id"] == "state.total_words_reconcile" and item["status"] == doctor_module.CHECK_WARNING
    ]
