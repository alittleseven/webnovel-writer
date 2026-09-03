#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T10（M1）freeze/retcon v1 测试。

对应方案：05 §2.2（素材三层流转）、06 §10（manifest）、07 F-10/F-07、08 T10。
契约：freeze 快照活层→定版 v{NN} + manifest（sha1）+ journal；
重复冻结拒绝；retcon 记录三选项裁决 + 事件。
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.domain_contract import init_domain_skeleton

    init_domain_skeleton(tmp_path)
    (tmp_path / "素材" / "活" / "桥段.csv").write_text("id,名称\nTR-1,测试桥段\n", encoding="utf-8", newline="\n")
    (tmp_path / "素材" / "活" / "场景写法.csv").write_text("id,名称\nSP-1,码头夜战\n", encoding="utf-8", newline="\n")
    return tmp_path


class TestFreeze:
    def test_freeze_snapshots_live_layer(self, book: Path):
        from data_modules.freeze_manager import freeze_volume

        report = freeze_volume(book, volume=2)

        assert report["ok"] is True
        snapshot = book / "素材" / "定版" / "v02"
        assert (snapshot / "桥段.csv").is_file()
        assert (snapshot / "场景写法.csv").is_file()

    def test_manifest_has_sha1_and_volume(self, book: Path):
        import json

        from data_modules.freeze_manager import freeze_volume

        freeze_volume(book, volume=2)
        manifest = json.loads((book / "素材" / "定版" / "v02" / "manifest.json").read_text(encoding="utf-8"))

        assert manifest["volume"] == 2
        paths = [f["path"] for f in manifest["source_files"]]
        assert "桥段.csv" in paths and "场景写法.csv" in paths
        assert all("sha1" in f and f["sha1"] for f in manifest["source_files"])

    def test_freeze_records_journal(self, book: Path):
        from data_modules.author_journal import read_journal
        from data_modules.freeze_manager import freeze_volume

        freeze_volume(book, volume=2)

        assert any(e["action"] == "freeze" for e in read_journal(book))

    def test_second_freeze_rejected(self, book: Path):
        from data_modules.freeze_manager import freeze_volume

        assert freeze_volume(book, volume=2)["ok"] is True
        report = freeze_volume(book, volume=2)
        assert report["ok"] is False
        assert report["error"] == "already_frozen"

    def test_force_refreeze(self, book: Path):
        from data_modules.freeze_manager import freeze_volume

        freeze_volume(book, volume=2)
        report = freeze_volume(book, volume=2, force=True)
        assert report["ok"] is True

    def test_empty_live_layer_warns_not_blocks(self, tmp_path: Path):
        from data_modules.domain_contract import init_domain_skeleton
        from data_modules.freeze_manager import freeze_volume

        init_domain_skeleton(tmp_path)
        report = freeze_volume(tmp_path, volume=3)
        assert report["ok"] is True
        assert report["warnings"], "空活层冻结应提示"

    def test_precondition_stale_reported(self, book: Path):
        from data_modules.author_journal import mark_stale
        from data_modules.freeze_manager import freeze_volume

        mark_stale(book, target="chapter:0040", reason="章纲被作者修改")
        report = freeze_volume(book, volume=2)

        assert report["ok"] is True
        assert any("stale" in w for w in report["warnings"])


class TestRetcon:
    def test_record_retcon_three_options(self, book: Path):
        from data_modules.author_journal import read_journal
        from data_modules.freeze_manager import record_retcon

        report = record_retcon(
            book,
            volume=2,
            choice="forward",
            reason="卷二战力规则调整",
            affected_chapters=[35, 38],
        )

        assert report["ok"] is True
        assert report["choice"] == "forward"
        events = read_journal(book)
        assert any(e["action"] == "retcon" for e in events)
        retcon_event = next(e for e in events if e["action"] == "retcon")
        assert "只改今后" in str(retcon_event.get("summary") or "")

    def test_invalid_choice_rejected(self, book: Path):
        from data_modules.freeze_manager import record_retcon

        report = record_retcon(book, volume=2, choice="炸掉重来", affected_chapters=[])
        assert report["ok"] is False
        assert report["error"] == "invalid_choice"

    def test_retcon_record_file_written(self, book: Path):
        from data_modules.freeze_manager import record_retcon

        record_retcon(book, volume=2, choice="full", reason="测试", affected_chapters=[1, 2])
        records = list((book / "演化").glob("retcon-v02-*.json"))
        assert len(records) == 1

    def test_retcon_options_enum(self, book: Path):
        from data_modules.freeze_manager import RETCON_CHOICES

        assert set(RETCON_CHOICES) == {"forward", "full", "revert"}
