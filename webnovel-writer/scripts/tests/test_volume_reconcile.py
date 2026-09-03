#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T30（M6）卷纲-实际对账测试。

对应方案：02 A7（卷收尾 diff 卷纲规划 vs 实际）、08 T30。
契约：节点覆盖率（节拍表危机链章节范围 vs 章纲卡/定稿正文）、伏笔兑现
（承诺账本状态统计）、战力里程碑（卷纲境界里程碑 vs 锚点通胀记录）三段对账；
报告落盘 大纲/卷纲/第NN卷-对账报告.md + journal。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.domain_contract import init_domain_skeleton
    from data_modules.power_anchor import apply_candidates, record_inflation
    from data_modules.promise_ledger import create_entry, update_status

    init_domain_skeleton(tmp_path)
    volume_dir = tmp_path / "大纲" / "卷纲"
    volume_dir.mkdir(parents=True, exist_ok=True)
    (volume_dir / "第02卷-节拍表.md").write_text(
        "# 第 2 卷 节拍表\n\n"
        "## 3) 升级危机链\n"
        "| 节点 | 危机/冲突 | 代价/风险升级 | 结果/变化 |\n"
        "|---|---|---|---|\n"
        "| 1 | 城南对峙（第41-50章） | 风险升级 | 据点扩容 |\n"
        "| 2 | 灾源争夺（第51-60章） | 风险再升级 | 主角受创 |\n"
        "| 3 | 北境之乱（第81-90章） | 最高风险 | 真相线索 |\n",
        encoding="utf-8",
    )
    (volume_dir / "第02卷.md").write_text(
        "# 第 2 卷：扩容与暗流\n\n"
        "> 卷末高潮：第90章 筑基圆满\n\n"
        "### 爽点密度规划\n- A级里程碑：第60章 筑基突破（中段）\n"
        "- 开局：炼气圆满后的余波收束（第41章前后）\n",
        encoding="utf-8",
    )
    # 实际：第41-50 章有定稿（节点1 覆盖），51-90 无（节点2/3 未覆盖）
    body_dir = tmp_path / "定稿" / "正文"
    body_dir.mkdir(parents=True, exist_ok=True)
    for chapter in (41, 45, 50):
        (body_dir / f"{chapter:04d}-章{chapter}.md").write_text(f"---\n章号: {chapter}\n---\n\n正文\n", encoding="utf-8")
    # 承诺：一条本卷已回收、一条本卷逾期、一条卷外
    create_entry(tmp_path, kind="伏笔", name="卷内已回收", planted_chapter=41, due_chapter=48)
    update_status(tmp_path, entry_id="F-001", status="已回收", chapter=47)
    create_entry(tmp_path, kind="伏笔", name="卷内逾期", planted_chapter=42, due_chapter=50)
    create_entry(tmp_path, kind="悬念", name="卷外", planted_chapter=10, due_chapter=200)
    # 战力：境界链 + 通胀记录（第45章 突破 筑基）
    apply_candidates(tmp_path, [
        {"序": 1, "名": "炼气", "差距描述": "", "寿元": ""},
        {"序": 2, "名": "筑基", "差距描述": "", "寿元": ""},
    ])
    record_inflation(tmp_path, chapter=45, anchor_point="筑基(1)", event="突破", milestone="卷二初筑基", deviation="提前2章")
    return tmp_path


class TestReconcile:
    def test_node_coverage(self, book: Path):
        from data_modules.volume_reconcile import reconcile_volume

        report = reconcile_volume(book, volume=2)

        nodes = report["node_coverage"]
        assert nodes[0]["covered"] is True, "第41-50章有定稿 → 节点1 覆盖"
        assert nodes[1]["covered"] is False and nodes[2]["covered"] is False
        assert report["coverage"] == round(1 / 3, 2)

    def test_fulfillment_counts(self, book: Path):
        from data_modules.volume_reconcile import reconcile_volume

        report = reconcile_volume(book, volume=2)
        counts = report["fulfillment"]

        assert counts == {"已回收": 1, "逾期": 1, "在途": 0}, "埋设章在本卷范围的条目按状态统计"

    def test_milestone_check(self, book: Path):
        from data_modules.volume_reconcile import reconcile_volume

        report = reconcile_volume(book, volume=2)
        milestones = report["milestones"]

        by_realm = {m["realm"]: m for m in milestones}
        assert "筑基" in by_realm
        assert by_realm["筑基"]["verified"] is True, "通胀记录第45章 筑基 → 已对账"
        assert by_realm["炼气"]["verified"] is False, "卷纲提及炼气但本卷无对应记录 → 未对账"

    def test_report_file_and_journal(self, book: Path):
        from data_modules.author_journal import read_journal
        from data_modules.volume_reconcile import reconcile_volume

        report = reconcile_volume(book, volume=2)

        assert Path(report["report_path"]).is_file()
        text = Path(report["report_path"]).read_text(encoding="utf-8")
        for section in ("节点覆盖率", "伏笔兑现", "战力里程碑"):
            assert section in text
        assert any(e["domain"] == "卷纲" and "对账" in str(e.get("summary")) for e in read_journal(book))

    def test_missing_volume_plan_fails_clean(self, book: Path):
        from data_modules.volume_reconcile import reconcile_volume

        assert reconcile_volume(book, volume=9)["error"] == "volume_plan_missing"
