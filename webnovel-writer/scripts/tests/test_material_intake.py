#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T13（M2）素材入口三通道测试。

对应方案：07 F-05（作者手写/AI 归纳/拆书投喂）、08 T13。
契约：AI 归纳与拆书投喂先进 `素材/regen/` 画廊、作者采纳才入活层（来源标记正确）；
作者直编走 author-sync 留账（已有行为，此处锁定域分类）；画廊只增不改，discard 才删。
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.domain_contract import init_domain_skeleton

    init_domain_skeleton(tmp_path)
    return tmp_path


def _candidate_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    columns = ["表", "id", "名称", "分类", "核心摘要", "详细展开", "正例", "反例", "备注"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture()
def ai_candidates(tmp_path: Path) -> Path:
    return _candidate_csv(
        tmp_path / "ai候选.csv",
        [
            {"表": "桥段", "id": "AI-001", "名称": "双线汇合反转", "分类": "桥段", "核心摘要": "摘要A"},
            {"表": "梗与反差", "id": "AI-002", "名称": "严肃场合报菜名", "分类": "梗", "核心摘要": "摘要B"},
        ],
    )


@pytest.fixture()
def book_candidates(tmp_path: Path) -> Path:
    return _candidate_csv(
        tmp_path / "拆书候选.csv",
        [{"表": "场景", "id": "CS-100", "名称": "雨夜天台谈判", "分类": "场景", "核心摘要": "摘要C"}],
    )


class TestPropose:
    def test_propose_ai_channel_writes_gallery(self, book: Path, ai_candidates: Path):
        from data_modules.author_journal import read_journal
        from data_modules.material_intake import list_candidates, propose_entries

        report = propose_entries(book, channel="AI归纳", file=ai_candidates)

        assert report["ok"] is True
        assert report["rows"] == 2
        batches = list_candidates(book)
        assert len(batches) == 1
        assert batches[0]["channel"] == "AI归纳"
        assert any(e["action"] == "regen" and e["domain"] == "素材" for e in read_journal(book))

    def test_propose_book_channel_keeps_source(self, book: Path, book_candidates: Path):
        from data_modules.material_intake import list_candidates, propose_entries

        report = propose_entries(book, channel="拆书:诡秘之主", file=book_candidates)

        assert report["ok"] is True
        assert list_candidates(book)[0]["channel"] == "拆书:诡秘之主"

    def test_propose_invalid_channel_rejected(self, book: Path, ai_candidates: Path):
        from data_modules.material_intake import propose_entries

        report = propose_entries(book, channel="作者手写", file=ai_candidates)
        assert report["ok"] is False
        assert report["error"] == "invalid_channel"

    def test_propose_unknown_table_rejected(self, book: Path, tmp_path: Path):
        from data_modules.material_intake import propose_entries

        bad = _candidate_csv(tmp_path / "bad.csv", [{"表": "不存在的表", "id": "X-1", "名称": "n"}])
        report = propose_entries(book, channel="AI归纳", file=bad)

        assert report["ok"] is False
        assert report["error"] == "invalid_table"

    def test_propose_missing_file_rejected(self, book: Path):
        from data_modules.material_intake import propose_entries

        report = propose_entries(book, channel="AI归纳", file=book / "无此文件.csv")
        assert report["ok"] is False
        assert report["error"] == "file_missing"


class TestAdopt:
    def test_adopt_routes_rows_into_tables_with_source(self, book: Path, ai_candidates: Path):
        from data_modules.author_journal import read_journal
        from data_modules.material_store import read_table
        from data_modules.material_intake import adopt_entries, propose_entries

        propose_entries(book, channel="AI归纳", file=ai_candidates)
        batch = "ai-v1.csv"
        report = adopt_entries(book, batch=batch)

        assert report["ok"] is True
        assert report["adopted"] == 2
        bridge = read_table(book, "桥段")
        assert bridge[0]["id"] == "AI-001" and bridge[0]["来源"] == "AI归纳", "来源标记正确"
        trope = read_table(book, "梗与反差")
        assert trope[0]["id"] == "AI-002" and trope[0]["来源"] == "AI归纳"
        assert any(e["action"] == "adopt" and e["domain"] == "素材" for e in read_journal(book))

    def test_adopt_short_table_alias(self, book: Path, book_candidates: Path):
        from data_modules.material_store import read_table
        from data_modules.material_intake import adopt_entries, propose_entries

        propose_entries(book, channel="拆书:诡秘之主", file=book_candidates)
        adopt_entries(book, batch="chaishu-v1.csv")
        rows = read_table(book, "场景写法")

        assert rows[0]["id"] == "CS-100"
        assert rows[0]["来源"] == "拆书:诡秘之主", "拆书出处随行入库"

    def test_adopt_duplicate_id_skipped(self, book: Path, ai_candidates: Path):
        from data_modules.material_intake import adopt_entries, propose_entries

        propose_entries(book, channel="AI归纳", file=ai_candidates)
        adopt_entries(book, batch="ai-v1.csv")
        report = adopt_entries(book, batch="ai-v1.csv")

        assert report["ok"] is True
        assert report["adopted"] == 0
        assert len(report["skipped"]) == 2

    def test_adopt_ids_subset(self, book: Path, ai_candidates: Path):
        from data_modules.material_store import read_table
        from data_modules.material_intake import adopt_entries, propose_entries

        propose_entries(book, channel="AI归纳", file=ai_candidates)
        adopt_entries(book, batch="ai-v1.csv", ids=["AI-002"])

        assert [r["id"] for r in read_table(book, "梗与反差")] == ["AI-002"]
        assert read_table(book, "桥段") == []

    def test_adopt_missing_batch_rejected(self, book: Path):
        from data_modules.material_intake import adopt_entries

        report = adopt_entries(book, batch="ghost-v9.csv")
        assert report["ok"] is False
        assert report["error"] == "batch_missing"


class TestDiscard:
    def test_discard_removes_batch(self, book: Path, ai_candidates: Path):
        from data_modules.author_journal import read_journal
        from data_modules.material_intake import discard_batch, list_candidates, propose_entries

        propose_entries(book, channel="AI归纳", file=ai_candidates)
        report = discard_batch(book, batch="ai-v1.csv")

        assert report["ok"] is True
        assert list_candidates(book) == []
        assert any(e["action"] == "discard" and e["domain"] == "素材" for e in read_journal(book))


class TestThreeChannels:
    def test_three_channels_each_land_one_entry(self, book: Path, tmp_path: Path):
        """T13 验收：三通道各入一条，来源标记正确。"""
        from data_modules.author_sync import classify_path
        from data_modules.material_store import append_entries, read_table
        from data_modules.material_intake import adopt_entries, propose_entries

        # 通道① 作者直编：author-sync 域分类兜底（模拟一行手写）
        assert classify_path("素材/活/台词金句.csv") == "素材"
        append_entries(book, "台词金句", [{"id": "GJ-001", "名称": "纸比人命贵"}], source="作者手写")

        # 通道② AI 归纳：画廊 → 采纳
        ai_file = _candidate_csv(
            tmp_path / "ai.csv", [{"表": "桥段", "id": "AI-001", "名称": "候选桥段"}]
        )
        propose_entries(book, channel="AI归纳", file=ai_file)
        adopt_entries(book, batch="ai-v1.csv", ids=["AI-001"])

        # 通道③ 拆书投喂：画廊 → 采纳
        cs_file = _candidate_csv(
            tmp_path / "cs.csv", [{"表": "场景", "id": "CS-100", "名称": "候选场景"}]
        )
        propose_entries(book, channel="拆书:某书", file=cs_file)
        adopt_entries(book, batch="chaishu-v1.csv", ids=["CS-100"])

        assert read_table(book, "台词金句")[0]["来源"] == "作者手写"
        assert read_table(book, "桥段")[0]["来源"] == "AI归纳"
        assert read_table(book, "场景写法")[0]["来源"] == "拆书:某书"


class TestCLI:
    def test_cli_propose_candidates_adopt(self, book: Path, ai_candidates: Path, capsys):
        from data_modules.material_store import main

        assert main(["propose", "--channel", "AI归纳", "--file", str(ai_candidates), "--project-root", str(book)]) == 0
        assert main(["candidates", "--project-root", str(book)]) == 0
        assert main(["adopt", "--batch", "ai-v1.csv", "--ids", "AI-001", "--project-root", str(book)]) == 0
        out = capsys.readouterr().out
        assert "ai-v1.csv" in out and "采纳 1 条" in out
