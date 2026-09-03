#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T11（M2）素材数据面测试。

对应方案：05 §2.2（素材三层流转）、06 §7（CSV 列约定）、07 F-05、08 T11。
契约：10 张活层表读写 + 校验；装配选择器只取「定版（带版本）+ 活层 active top-K」；
init 播种按题材子集（≈4 表 × ≤30 条，D0-5），来源=播种:<题材包>，不覆盖既有表。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.domain_contract import init_domain_skeleton

    init_domain_skeleton(tmp_path)
    return tmp_path


def _add_live(book: Path, table: str, rows: list[dict[str, str]]) -> None:
    from data_modules.material_store import SKELETON_COLUMNS, material_csv_path

    path = material_csv_path(book, table)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(SKELETON_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def _live_row(id_: str, name: str = "条目", status: str = "active", source: str = "作者手写") -> dict[str, str]:
    return {
        "id": id_,
        "名称": name,
        "分类": "测试",
        "核心摘要": "摘要",
        "详细展开": "展开",
        "正例": "正",
        "反例": "反",
        "来源": source,
        "状态": status,
        "备注": "",
    }


class TestTables:
    def test_ten_tables_declared(self):
        from data_modules.material_store import MATERIAL_TABLES

        assert len(MATERIAL_TABLES) == 10
        assert set(MATERIAL_TABLES) == {
            "桥段", "爽点节奏", "人设关系", "场景写法", "写作技法",
            "命名风格", "金手指零件", "世界观零件", "台词金句", "梗与反差",
        }

    def test_read_table_roundtrip(self, book: Path):
        from data_modules.material_store import read_table

        _add_live(book, "桥段", [_live_row("TR-001"), _live_row("TR-002")])
        rows = read_table(book, "桥段")

        assert [r["id"] for r in rows] == ["TR-001", "TR-002"]

    def test_read_table_missing_returns_empty(self, book: Path):
        from data_modules.material_store import read_table

        assert read_table(book, "梗与反差") == []

    def test_append_entries_assigns_source_and_status(self, book: Path):
        from data_modules.author_journal import read_journal
        from data_modules.material_store import append_entries, read_table

        report = append_entries(
            book, "台词金句", [{"id": "GJ-001", "名称": "纸比人命贵", "核心摘要": "金句"}], source="AI归纳"
        )

        assert report["ok"] is True
        rows = read_table(book, "台词金句")
        assert rows[0]["来源"] == "AI归纳"
        assert rows[0]["状态"] == "active"
        assert any(e["domain"] == "素材" for e in read_journal(book))

    def test_append_duplicate_id_rejected(self, book: Path):
        from data_modules.material_store import append_entries

        append_entries(book, "桥段", [{"id": "TR-001", "名称": "a"}])
        report = append_entries(book, "桥段", [{"id": "TR-001", "名称": "b"}])

        assert report["ok"] is False
        assert report["error"] == "duplicate_id"

    def test_validate_reports_problems(self, book: Path):
        from data_modules.material_store import validate_tables

        _add_live(book, "桥段", [_live_row("TR-001", status="失踪"), _live_row("TR-001")])
        problems = validate_tables(book)

        assert any("TR-001" in p and "重复" in p for p in problems)
        assert any("失踪" in p for p in problems)

    def test_validate_clean_book_passes(self, book: Path):
        from data_modules.material_store import validate_tables

        _add_live(book, "场景写法", [_live_row("SP-007")])
        assert validate_tables(book) == []


class TestAssemble:
    def _freeze(self, book: Path, volume: int = 1) -> None:
        from data_modules.freeze_manager import freeze_volume

        freeze_volume(book, volume=volume)

    def test_assemble_takes_frozen_plus_live_topk(self, book: Path):
        from data_modules.material_store import append_entries, assemble_materials

        _add_live(book, "桥段", [_live_row(f"TR-{i:03d}") for i in range(1, 6)])
        self._freeze(book)
        append_entries(book, "桥段", [{"id": "TR-101", "名称": "新增"}], source="AI归纳")

        report = assemble_materials(book, tables=["桥段"], k=3)

        frozen = report["frozen"]["桥段"]
        live = report["live"]["桥段"]
        assert frozen["version"] == 1
        assert len(frozen["rows"]) == 5
        assert len(live) == 3, "活层必须截断到 top-K"

    def test_assemble_excludes_archived(self, book: Path):
        from data_modules.material_store import assemble_materials

        _add_live(
            book, "桥段",
            [_live_row("TR-001"), _live_row("TR-002", status="归档"), _live_row("TR-003", status="衰减")],
        )

        report = assemble_materials(book, tables=["桥段"], k=10)

        live_ids = [r["id"] for r in report["live"]["桥段"]]
        assert live_ids == ["TR-001"], "归档与衰减条目不进装配"

    def test_assemble_specific_frozen_version(self, book: Path):
        from data_modules.material_store import assemble_materials

        _add_live(book, "桥段", [_live_row("TR-001")])
        self._freeze(book, volume=1)
        _add_live(book, "桥段", [_live_row("TR-002")])
        self._freeze(book, volume=2)

        report = assemble_materials(book, tables=["桥段"], version=1)

        assert report["frozen"]["桥段"]["version"] == 1
        assert [r["id"] for r in report["frozen"]["桥段"]["rows"]] == ["TR-001"]

    def test_assemble_no_frozen_yields_empty_frozen(self, book: Path):
        from data_modules.material_store import assemble_materials

        _add_live(book, "桥段", [_live_row("TR-001")])
        report = assemble_materials(book, tables=["桥段"], k=5)

        assert report["frozen"] == {} or report["frozen"].get("桥段") is None


class TestSeed:
    @pytest.fixture()
    def source_dir(self, tmp_path: Path) -> Path:
        src = tmp_path / "src_csv"
        src.mkdir()
        base_header = ["编号", "适用技能", "分类", "层级", "关键词", "意图与同义词", "适用题材", "大模型指令", "核心摘要", "详细展开"]
        bridge_rows = [
            ["TR-001", "write", "桥段", "知识补充", "k", "i", "玄幻|仙侠", "cmd", "摘要1", "展开1", "退婚流", "爽点1", "毒点1"],
            ["TR-002", "write", "桥段", "知识补充", "k", "i", "全部", "cmd", "摘要2", "展开2", "火葬场", "爽点2", "毒点2"],
            ["TR-003", "write", "桥段", "知识补充", "k", "i", "现言", "cmd", "摘要3", "展开3", "契约婚姻", "爽点3", "毒点3"],
        ]
        _write_csv(src / "桥段套路.csv", base_header + ["桥段名称", "核心爽点", "毒点"], bridge_rows)
        rhythm_rows = [
            [f"PA-{i:03d}", "write", "节奏", "知识补充", "k", "i", "玄幻" if i % 2 else "全部", "cmd", f"摘{i}", f"展{i}", "小爆发", "手法", "毒"]
            for i in range(1, 41)
        ]
        _write_csv(src / "爽点与节奏.csv", base_header + ["节奏类型", "情绪调动手法", "毒点"], rhythm_rows)
        relation_rows = [
            ["CH-001", "write", "人设", "知识补充", "k", "i", "全部", "cmd", "摘要", "展开", "师徒", "动机", "逻辑", "模式", "毒点"],
        ]
        _write_csv(src / "人设与关系.csv", base_header + ["人设类型", "核心动机", "行为逻辑", "互动模式", "毒点"], relation_rows)
        craft_rows = [
            ["WT-001", "write", "技法", "知识补充", "k", "i", "玄幻", "cmd", "摘要", "展开", "类型", "留钩", "场景", "毒点", "正例W", "反例W"],
        ]
        _write_csv(src / "写作技法.csv", base_header + ["技法类型", "技法名称", "适用场景", "毒点", "正例", "反例"], craft_rows)
        return src

    def test_seed_filters_by_genre_and_caps(self, book: Path, source_dir: Path):
        from data_modules.material_store import seed_materials

        report = seed_materials(book, genre="玄幻", source_dir=source_dir)

        assert report["ok"] is True
        assert set(report["seeded"]) == {"桥段", "爽点节奏", "人设关系", "写作技法"}, "D0-5：默认播种 4 张核心表"
        rows = report["rows"]["桥段"]
        assert len(rows) == 2, "玄幻命中 TR-001（玄幻|仙侠）+ TR-002（全部），排除现言 TR-003"
        assert all(r["来源"] == "播种:玄幻" for r in rows)
        assert all(r["状态"] == "active" for r in rows)

    def test_seed_caps_per_table_limit(self, book: Path, source_dir: Path):
        from data_modules.material_store import read_table, seed_materials

        seed_materials(book, genre="玄幻", source_dir=source_dir)
        rows = read_table(book, "爽点节奏")

        assert len(rows) == 30, "每表上限 30 条（D0-5）"

    def test_seed_skips_existing_tables(self, book: Path, source_dir: Path):
        from data_modules.material_store import seed_materials

        first = seed_materials(book, genre="玄幻", source_dir=source_dir)
        second = seed_materials(book, genre="都市", source_dir=source_dir)

        assert first["ok"] is True
        assert second["seeded"] == {}, "播种不覆盖既有表（作者主权）"

    def test_seed_unknown_genre_takes_only_generic_rows(self, book: Path, source_dir: Path):
        from data_modules.material_store import seed_materials

        report = seed_materials(book, genre="未知题材", source_dir=source_dir)

        assert report["ok"] is True
        assert [r["id"] for r in report["rows"]["桥段"]] == ["TR-002"], "未命中题材只取「全部」行"

    def test_seed_from_plugin_references(self, book: Path):
        from data_modules.material_store import default_source_dir, seed_materials

        assert (default_source_dir() / "桥段套路.csv").is_file()
        report = seed_materials(book, genre="都市")

        assert report["ok"] is True
        assert len(report["rows"]["桥段"]) <= 30
        assert report["rows"]["桥段"], "真实参考库播种应有产出"

    def test_init_project_seeds_materials(self, tmp_path: Path):
        import sys

        scripts_dir = Path(__file__).resolve().parent.parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from init_project import init_project

        target = tmp_path / "newbook"
        init_project(str(target), "测试书", "都市")

        seeded = target / "素材" / "活" / "桥段.csv"
        assert seeded.is_file(), "新 init 项目应含播种素材（T11 验收）"
        with seeded.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        assert rows and all(r["来源"].startswith("播种:") for r in rows)
        assert (target / "作者" / "journal.jsonl").is_file(), "init 同时补齐六域骨架"
