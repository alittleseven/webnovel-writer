#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T28（M6）承诺账本与逾期扫描测试。

对应方案：05 §1（大纲/条目 三类承诺账本）、06 §12-4（条目状态机）、02 A3
（foreshadow-scan 承诺账本×最晚回收章×当前章号）、08 T28。
契约：条目 front matter 读写（伏笔F/悬念S/感情线R，状态机 open→推进中→已回收/作废，
逾期由扫描器标记）；foreshadow-scan 构造逾期用例全报出；pending 给 write 链
「本章应推进项」（逾期+即将到期+章纲卡承诺推进）。
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.domain_contract import init_domain_skeleton
    from data_modules.promise_ledger import create_entry

    init_domain_skeleton(tmp_path)
    create_entry(tmp_path, kind="伏笔", name="熔炉残响", planted_chapter=12, due_chapter=50)
    create_entry(tmp_path, kind="伏笔", name="林知夏身世", planted_chapter=20, due_chapter=45)
    create_entry(tmp_path, kind="悬念", name="天裂是什么", planted_chapter=1, due_chapter=200)
    create_entry(tmp_path, kind="感情线", name="知夏靠近", planted_chapter=6, due_chapter=80)
    return tmp_path


class TestEntries:
    def test_create_assigns_prefix_ids(self, book: Path):
        from data_modules.author_journal import read_journal
        from data_modules.promise_ledger import load_entries

        entries = load_entries(book)

        assert [e["编号"] for e in entries] == ["F-001", "F-002", "R-001", "S-001"], "按类型前缀独立编号"
        assert entries[0]["状态"] == "open"
        assert entries[0]["埋设章"] == 12 and entries[0]["最晚回收章"] == 50
        assert any(e["action"] == "add" and e["domain"] == "条目" for e in read_journal(book))

    def test_load_entries_filter_kind(self, book: Path):
        from data_modules.promise_ledger import load_entries

        assert [e["编号"] for e in load_entries(book, kind="悬念")] == ["S-001"]

    def test_update_status_state_machine(self, book: Path):
        from data_modules.author_journal import read_journal
        from data_modules.promise_ledger import load_entries, update_status

        assert update_status(book, entry_id="F-001", status="推进中")["ok"] is True
        report = update_status(book, entry_id="F-001", status="已回收", chapter=44)

        assert report["ok"] is True
        entry = next(e for e in load_entries(book) if e["编号"] == "F-001")
        assert entry["状态"] == "已回收" and entry["回收章"] == 44

    def test_illegal_transition_rejected(self, book: Path):
        from data_modules.promise_ledger import update_status

        update_status(book, entry_id="F-001", status="已回收", chapter=44)
        report = update_status(book, entry_id="F-001", status="推进中")

        assert report["ok"] is False
        assert report["error"] == "illegal_transition"

    def test_unknown_entry_rejected(self, book: Path):
        from data_modules.promise_ledger import update_status

        assert update_status(book, entry_id="X-999", status="推进中")["error"] == "not_found"


class TestForeshadowScan:
    def test_overdue_all_reported_and_marked(self, book: Path):
        """T28 验收：构造逾期用例全报出。"""
        from data_modules.promise_ledger import foreshadow_scan, load_entries

        report = foreshadow_scan(book, current_chapter=60)

        overdue_ids = {e["编号"] for e in report["overdue"]}
        assert overdue_ids == {"F-001", "F-002"}, "最晚回收章 50/45 < 当前 60：两条全报出"
        assert "S-001" not in overdue_ids, "未到期不报"
        marked = {e["编号"]: e["状态"] for e in load_entries(book)}
        assert marked["F-001"] == "逾期" and marked["F-002"] == "逾期"
        assert marked["S-001"] == "open"

    def test_scan_idempotent_and_recovered_not_flagged(self, book: Path):
        from data_modules.author_journal import read_journal
        from data_modules.promise_ledger import foreshadow_scan, update_status

        update_status(book, entry_id="F-002", status="已回收", chapter=44)
        first = foreshadow_scan(book, current_chapter=60)
        second = foreshadow_scan(book, current_chapter=60)

        # 已回收的 F-002 不再报；F-001 未回收前持续报出（门禁语义）
        assert {e["编号"] for e in first["overdue"]} == {"F-001"}
        assert {e["编号"] for e in second["overdue"]} == {"F-001"}
        mark_events = [e for e in read_journal(book) if e["domain"] == "条目" and "逾期" in str(e.get("summary"))]
        assert len(mark_events) == 1, "重复扫描不重复写标记 journal"

    def test_due_soon_window(self, book: Path):
        from data_modules.promise_ledger import foreshadow_scan

        report = foreshadow_scan(book, current_chapter=73)

        due_soon = {e["编号"] for e in report["due_soon"]}
        assert "R-001" in due_soon, "最晚回收章 80 在 10 章窗内 → 即将到期"
        assert "S-001" not in due_soon, "最晚回收章 200 超窗不报"


class TestPendingForChapter:
    def test_pending_lists_write_chain_items(self, book: Path):
        from data_modules.promise_ledger import foreshadow_scan, pending_for_chapter

        foreshadow_scan(book, current_chapter=60)
        report = pending_for_chapter(book, chapter=61)

        ids = {i["编号"] for i in report["items"]}
        assert "F-001" in ids and "F-002" in ids, "逾期条目进入本章应推进项"
        assert report["from_card"] == [], "无章纲卡时为空"

    def test_pending_consumes_card_refs(self, book: Path, tmp_path_factory):
        from data_modules.chapter_outline_batch import create_chapter_batch
        from data_modules.promise_ledger import pending_for_chapter

        create_chapter_batch(
            book,
            [{
                "章节号": 61, "标题": "还债", "卷": 2, "时间锚": "第61天",
                "节点": ["CBN: x"], "字数目标": 2000,
                "承诺推进": ["F-001: 熔炉残响第一次异动"],
            }],
        )

        report = pending_for_chapter(book, chapter=61)

        assert report["from_card"] == ["F-001: 熔炉残响第一次异动"]


class TestCLI:
    def test_cli_scan_and_pending(self, book: Path, capsys):
        from data_modules.promise_ledger import main

        code = main(["scan", "--chapter", "60", "--project-root", str(book)])
        assert code == 1, "存在逾期时非零退出（门禁语义）"
        assert main(["pending", "--chapter", "61", "--project-root", str(book), "--format", "json"]) == 0
        out = capsys.readouterr().out
        assert "F-001" in out
