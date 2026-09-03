#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T12（M2）使用轨迹与写作接线测试。

对应方案：06 §1（使用轨迹.jsonl）、07 F-05（settle 后写轨迹）/F-11（settle 追加）、08 T12。
契约：轨迹 append-only（残行容错）；章纲卡素材引用消费（表:ID 解析 → 定版版本判定）；
settle_materials_for_chapter 供 chapter-commit 落账调用；引用缺失不阻断、只告警。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.chapter_outline_batch import create_chapter_batch
    from data_modules.domain_contract import init_domain_skeleton
    from data_modules.freeze_manager import freeze_volume
    from data_modules.material_store import append_entries

    init_domain_skeleton(tmp_path)
    append_entries(tmp_path, "桥段", [{"id": "TR-001", "名称": "退婚三年之约", "核心摘要": "摘要"}])
    append_entries(
        tmp_path, "场景写法", [{"id": "SP-007", "名称": "码头夜战", "核心摘要": "摘要"}]
    )
    freeze_volume(tmp_path, volume=1)
    # SP-007 从活层移除（模拟冻结后作者清理）→ 只存在于定版 v01
    live_csv = tmp_path / "素材" / "活" / "场景写法.csv"
    lines = live_csv.read_text(encoding="utf-8-sig").splitlines()
    live_csv.write_text("\n".join(line for line in lines if "SP-007" not in line) + "\n", encoding="utf-8", newline="\n")
    create_chapter_batch(
        tmp_path,
        [
            {
                "章节号": 39,
                "标题": "纸债",
                "卷": 2,
                "时间锚": "第41日·夜",
                "节点": ["CBN: 发现账本异常"],
                "字数目标": 2400,
                "素材引用": ["桥段:TR-001", "场景:SP-007", "梗与反差:GK-999"],
            }
        ],
    )
    return tmp_path


class TestTrajectory:
    def test_append_and_read_roundtrip(self, book: Path):
        from data_modules.material_usage import append_usage, read_trajectory

        count = append_usage(book, 39, [{"条目id": "TR-001", "定版版本": "live", "用法": "章纲引用"}])

        assert count == 1
        rows = read_trajectory(book)
        assert rows[0]["章"] == 39
        assert rows[0]["条目id"] == "TR-001"
        assert rows[0]["定版版本"] == "live"
        assert rows[0]["用法"] == "章纲引用"
        assert rows[0]["ts"]

    def test_trajectory_filter_by_chapter(self, book: Path):
        from data_modules.material_usage import append_usage, read_trajectory

        append_usage(book, 39, [{"条目id": "TR-001", "定版版本": "live", "用法": "章纲引用"}])
        append_usage(book, 40, [{"条目id": "TR-001", "定版版本": "live", "用法": "正文复用"}])

        assert len(read_trajectory(book)) == 2
        assert [r["章"] for r in read_trajectory(book, chapter=40)] == [40]

    def test_trajectory_tolerates_broken_tail(self, book: Path):
        from data_modules.material_usage import append_usage, read_trajectory, trajectory_path

        append_usage(book, 39, [{"条目id": "TR-001", "定版版本": "live", "用法": "x"}])
        with trajectory_path(book).open("a", encoding="utf-8") as f:
            f.write('{"章": 40, "条目id": "TR-001"')  # 模拟崩溃残行

        assert len(read_trajectory(book)) == 1


class TestResolveRef:
    def test_resolve_live_and_frozen(self, book: Path):
        from data_modules.material_usage import resolve_ref

        live = resolve_ref(book, "桥段:TR-001")
        assert live == {"ok": True, "table": "桥段", "id": "TR-001", "version": "live"}

        frozen = resolve_ref(book, "场景写法:SP-007")
        assert frozen == {"ok": True, "table": "场景写法", "id": "SP-007", "version": "v01"}

    def test_resolve_missing_ref(self, book: Path):
        from data_modules.material_usage import resolve_ref

        report = resolve_ref(book, "梗与反差:GK-999")
        assert report["ok"] is False
        assert report["reason"] == "not_found"

    def test_resolve_unknown_table(self, book: Path):
        from data_modules.material_usage import resolve_ref

        assert resolve_ref(book, "不存在的表:X-1")["ok"] is False

    def test_resolve_bare_id_searches_all_tables(self, book: Path):
        from data_modules.material_usage import resolve_ref

        report = resolve_ref(book, "TR-001")
        assert report["ok"] is True
        assert report["table"] == "桥段"


class TestLogChapterMaterials:
    def test_log_consumes_card_refs(self, book: Path):
        from data_modules.author_journal import read_journal
        from data_modules.material_usage import log_chapter_materials, read_trajectory

        report = log_chapter_materials(book, 39)

        assert report["ok"] is True
        assert len(report["logged"]) == 2, "TR-001（live）+ SP-007（v01）落账"
        versions = {row["条目id"]: row["定版版本"] for row in read_trajectory(book)}
        assert versions == {"TR-001": "live", "SP-007": "v01"}
        assert report["missing"] == ["梗与反差:GK-999"], "缺失引用只告警不落账"
        settle = [e for e in read_journal(book) if e["action"] == "settle" and e["domain"] == "素材"]
        assert settle and "39" in settle[-1]["summary"]

    def test_log_idempotent_per_chapter(self, book: Path):
        """重复落账拒绝（一章一批轨迹；重跑需 --force 或先清理）。"""
        from data_modules.material_usage import log_chapter_materials

        assert log_chapter_materials(book, 39)["ok"] is True
        report = log_chapter_materials(book, 39)

        assert report["ok"] is False
        assert report["error"] == "already_logged"

    def test_log_without_card_fails_clean(self, book: Path):
        from data_modules.material_usage import log_chapter_materials

        report = log_chapter_materials(book, 99)
        assert report["ok"] is False
        assert report["error"] == "card_missing"

    def test_settle_hook_writes_trajectory(self, book: Path):
        """chapter-commit 落账钩子：静默成功，无卡/失败不抛异常。"""
        from data_modules.material_usage import read_trajectory, settle_materials_for_chapter

        assert settle_materials_for_chapter(book, 39) is True
        assert len(read_trajectory(book)) == 2
        assert settle_materials_for_chapter(book, 39) is False, "重复落账返回 False 不抛错"
        assert settle_materials_for_chapter(book, 99) is False, "无章纲卡静默跳过"

    def test_cli_log_and_trajectory(self, book: Path, capsys):
        from data_modules.material_store import main

        assert main(["log", "--chapter", "39", "--project-root", str(book)]) == 0
        assert main(["trajectory", "--chapter", "39", "--project-root", str(book)]) == 0
        out = capsys.readouterr().out
        assert "TR-001" in out and "39" in out
