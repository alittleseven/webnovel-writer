"""Tests for timeline_check integration into prewrite gate (P0-4)."""
import json
import pytest
from pathlib import Path

from data_modules.write_gates.prewrite import run_prewrite_gate


def _setup_project(tmp_path: Path) -> Path:
    """Create minimal project structure."""
    root = tmp_path / "book"
    (root / ".webnovel").mkdir(parents=True)
    state = {
        "project_info": {"genre": "玄幻"},
        "progress": {"current_chapter": 1, "total_words": 0},
    }
    (root / ".webnovel" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return root


class TestPrewriteGateTimeline:
    def test_timeline_check_called_for_volume(self, tmp_path, monkeypatch):
        """prewrite gate should invoke timeline check and include results in report."""
        root = _setup_project(tmp_path)
        called = {}

        def fake_check(root_path, volume_num):
            called["volume"] = volume_num
            return {"ok": True, "errors": [], "warnings": []}

        monkeypatch.setattr(
            "data_modules.write_gates.prewrite.check_timeline", fake_check
        )
        report = run_prewrite_gate(root, chapter=1)
        assert "timeline" in str(report.get("details", {}).keys()).lower() or \
            any("timeline" in e.get("code", "") for e in report.get("errors", []) + report.get("warnings", []))

    def test_timeline_error_produces_warning(self, tmp_path, monkeypatch):
        """A failed timeline check should produce a warning issue in the gate report."""
        root = _setup_project(tmp_path)

        def fake_check(root_path, volume_num):
            return {"ok": False, "errors": [{"message": "时间回跳"}], "warnings": []}

        monkeypatch.setattr(
            "data_modules.write_gates.prewrite.check_timeline", fake_check
        )
        report = run_prewrite_gate(root, chapter=1)
        # Timeline failure is warning-level (not blocking prewrite entirely)
        all_issues = report.get("errors", []) + report.get("warnings", [])
        assert any("timeline" in i.get("code", "").lower() for i in all_issues), \
            f"Expected timeline issue in gate report, got: {report}"
