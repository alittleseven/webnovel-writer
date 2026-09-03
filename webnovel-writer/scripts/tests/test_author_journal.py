#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T2（M0）journal 数据面测试。

对应方案：docs/zcode/webnovel-copilot-300/06-data-design.md §3/§4。
契约：journal.jsonl 一行一事 append-only（水位/回放/校验）；
stale.json 可重建、消费标记流转。
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.domain_contract import init_domain_skeleton

    init_domain_skeleton(tmp_path)
    return tmp_path


def _make_event(**overrides) -> dict:
    base = {
        "ts": "2026-09-03T10:00:00+08:00",
        "actor": "author",
        "action": "edit",
        "domain": "章纲",
        "path": "大纲/章纲/0039.md",
        "change_kind": "content",
        "diff_stat": {"ins": 3, "del": 1},
        "summary": "",
        "impact": [],
    }
    base.update(overrides)
    return base


class TestJournalAppendRead:
    def test_append_then_read_roundtrip(self, book: Path):
        from data_modules.author_journal import append_events, read_journal

        append_events(book, [_make_event(), _make_event(action="adopt", domain="素材")])

        events = read_journal(book)
        assert len(events) == 2
        assert events[0]["action"] == "edit"
        assert events[1]["domain"] == "素材"

    def test_append_is_atomic_line_per_event(self, book: Path):
        from data_modules.author_journal import append_events

        append_events(book, [_make_event(summary="多行\n摘要测试")])

        lines = (book / "作者" / "journal.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1, "一个事件必须恰占一行（summary 内嵌换行需转义）"

    def test_watermark_advances(self, book: Path):
        from data_modules.author_journal import append_events, read_watermark, write_watermark

        append_events(book, [_make_event()])
        write_watermark(book, 1)
        assert read_watermark(book) == 1
        append_events(book, [_make_event(action="freeze")])
        write_watermark(book, 2)
        assert read_watermark(book) == 2

    def test_watermark_defaults_to_zero(self, book: Path):
        from data_modules.author_journal import read_watermark

        assert read_watermark(book) == 0

    def test_read_after_watermark(self, book: Path):
        from data_modules.author_journal import append_events, read_journal, write_watermark

        append_events(book, [_make_event(), _make_event(action="freeze"), _make_event(action="retcon")])
        write_watermark(book, 1)
        pending = read_journal(book, after_index=1)
        assert [e["action"] for e in pending] == ["freeze", "retcon"]

    def test_torn_last_line_is_ignored(self, book: Path):
        journal = book / "作者" / "journal.jsonl"
        journal.write_text('{"ts": "t"}\n{"ts": "tor', encoding="utf-8")

        from data_modules.author_journal import read_journal

        events = read_journal(book)
        assert len(events) == 1, "末尾残行（崩溃中写入）应被忽略而非炸掉读取"

    def test_validate_flags_bad_events(self, book: Path):
        from data_modules.author_journal import append_events, validate_journal

        append_events(book, [_make_event(actor="unknown", domain="不存在域")])
        problems = validate_journal(book)
        assert any("actor" in p for p in problems)
        assert any("domain" in p for p in problems)


class TestStale:
    def test_mark_and_read(self, book: Path):
        from data_modules.author_journal import mark_stale, read_stale

        mark_stale(book, target="chapter:0039", reason="章纲被作者修改", impact=["context-stale:0039"])

        items = read_stale(book)
        assert len(items) == 1
        assert items[0]["target"] == "chapter:0039"
        assert items[0]["consumed"] is False

    def test_consume_stale(self, book: Path):
        from data_modules.author_journal import consume_stale, mark_stale, read_stale

        mark_stale(book, target="material:v01:TR-012", reason="定版素材修改")
        consume_stale(book, "material:v01:TR-012")

        items = read_stale(book)
        assert items[0]["consumed"] is True

    def test_stale_file_rebuildable(self, book: Path):
        # stale.json 丢失后 read 返回空（可重建语义：不炸、不误报）
        from data_modules.author_journal import read_stale

        assert read_stale(book) == []

    def test_mark_same_target_merges(self, book: Path):
        from data_modules.author_journal import mark_stale, read_stale

        mark_stale(book, target="chapter:0039", reason="a")
        mark_stale(book, target="chapter:0039", reason="b")

        items = read_stale(book)
        assert len(items) == 1
        assert items[0]["reason"] == "b"


class TestSemanticEnrichment:
    def test_pending_semantic_lists_empty_summaries(self, book: Path):
        from data_modules.author_journal import append_events, pending_semantic

        append_events(book, [_make_event(), _make_event(summary="已有摘要")])

        pending = pending_semantic(book)
        assert len(pending) == 1
        assert pending[0]["index"] == 1
        assert pending[0]["path"] == "大纲/章纲/0039.md"

    def test_pending_semantic_respects_batch_limit(self, book: Path):
        from data_modules.author_journal import append_events, pending_semantic

        append_events(book, [_make_event() for _ in range(7)])

        assert len(pending_semantic(book, batch_limit=5)) == 5

    def test_enrichment_appended_and_view_merged(self, book: Path):
        from data_modules.author_journal import append_enrichment, append_events, read_journal, read_journal_view

        append_events(book, [_make_event()])
        append_enrichment(book, ref_index=1, summary="把对峙从酒楼改到码头", change_kind="structure")

        raw = read_journal(book)
        assert len(raw) == 2, "enrich 是追加事件（append-only 红线）"
        view = read_journal_view(book)
        assert len(view) == 1, "视图中 enrich 不单独出现"
        assert view[0]["summary"] == "把对峙从酒楼改到码头"
        assert view[0]["change_kind"] == "structure"
        assert view[0]["enriched"] is True

    def test_last_enrichment_wins(self, book: Path):
        from data_modules.author_journal import append_enrichment, append_events, read_journal_view

        append_events(book, [_make_event()])
        append_enrichment(book, ref_index=1, summary="第一次补全")
        append_enrichment(book, ref_index=1, summary="第二次补全")

        view = read_journal_view(book)
        assert view[0]["summary"] == "第二次补全"
