#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T1（M0）书仓六域目录契约测试。

对应方案：docs/zcode/webnovel-copilot-300/05-book-directory-structure.md §1、08 T1。
契约：六域骨架（大纲/素材/设定/作者/文风/演化）；init 幂等且永不覆盖既有内容；
check 输出结构化报告（required 缺失=warning，advisory 缺失=info）。
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def v7_book(tmp_path: Path) -> Path:
    root = tmp_path / "my-novel"
    root.mkdir()
    (root / "book.yaml").write_text('spec_version: "7.2"\n书名: 测试书\n', encoding="utf-8")
    (root / "定稿" / "正文").mkdir(parents=True)
    (root / "大纲").mkdir()
    (root / "演化").mkdir()
    (root / "设定").mkdir()
    return root


class TestIsStoryRepo:
    def test_book_yaml_present(self, v7_book: Path):
        from data_modules.domain_contract import is_story_repo

        assert is_story_repo(v7_book) is True

    def test_plain_dir(self, tmp_path: Path):
        from data_modules.domain_contract import is_story_repo

        assert is_story_repo(tmp_path) is False


class TestInitDomainSkeleton:
    def test_creates_missing_skeleton(self, v7_book: Path):
        from data_modules.domain_contract import REQUIRED_DIRS, REQUIRED_FILES, init_domain_skeleton

        report = init_domain_skeleton(v7_book)

        assert report["created_dirs"], "应当创建缺失目录"
        for rel in REQUIRED_DIRS:
            assert (v7_book / rel).is_dir(), rel
        for rel in REQUIRED_FILES:
            assert (v7_book / rel).is_file(), rel
        assert (v7_book / "作者" / "journal.jsonl").exists()

    def test_idempotent_second_run(self, v7_book: Path):
        from data_modules.domain_contract import init_domain_skeleton

        init_domain_skeleton(v7_book)
        report = init_domain_skeleton(v7_book)

        assert report["created_dirs"] == []
        assert report["created_files"] == []
        assert report["skipped"], "第二次运行应全部跳过"

    def test_never_overwrites_existing_journal(self, v7_book: Path):
        from data_modules.domain_contract import init_domain_skeleton

        journal = v7_book / "作者" / "journal.jsonl"
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text('{"ts": "t0", "actor": "author"}\n', encoding="utf-8")

        init_domain_skeleton(v7_book)

        assert journal.read_text(encoding="utf-8") == '{"ts": "t0", "actor": "author"}\n'

    def test_creates_gitignore_entries_once(self, v7_book: Path):
        from data_modules.domain_contract import init_domain_skeleton

        init_domain_skeleton(v7_book)

        gi = v7_book / ".gitignore"
        assert gi.is_file()
        content = gi.read_text(encoding="utf-8")
        assert "工作区/" in content and ".cache/" in content
        # 第二次运行不重复追加
        init_domain_skeleton(v7_book)
        assert gi.read_text(encoding="utf-8") == content


class TestCheckDomainContract:
    def test_all_ok_after_init(self, v7_book: Path):
        from data_modules.domain_contract import check_domain_contract, init_domain_skeleton

        init_domain_skeleton(v7_book)
        report = check_domain_contract(v7_book)

        assert report["ok"] is True
        assert report["missing_required"] == []
        warnings = [i for i in report["items"] if i["status"] == "warning"]
        assert warnings == []

    def test_missing_journal_is_warning(self, v7_book: Path):
        from data_modules.domain_contract import check_domain_contract

        report = check_domain_contract(v7_book)

        assert report["ok"] is False  # required 缺失
        ids = {i["id"] for i in report["items"] if i["status"] == "warning"}
        assert any("journal" in i for i in ids)

    def test_advisory_missing_is_info_not_warning(self, v7_book: Path):
        from data_modules.domain_contract import check_domain_contract, init_domain_skeleton

        init_domain_skeleton(v7_book)
        report = check_domain_contract(v7_book)

        # 力量锚点/信息差/宪法/指纹此时都不存在 → 应为 info 建议而非 warning
        advisory = [i for i in report["items"] if i["id"].startswith("advisory.")]
        assert advisory, "advisory 检查项应存在"
        assert all(i["status"] == "info" for i in advisory)

    def test_existing_advisory_reported_ok(self, v7_book: Path):
        from data_modules.domain_contract import check_domain_contract, init_domain_skeleton

        init_domain_skeleton(v7_book)
        (v7_book / "设定" / "力量锚点.yaml").write_text("spec: power-anchor/1\n", encoding="utf-8")
        report = check_domain_contract(v7_book)

        anchor = next(i for i in report["items"] if i["id"] == "advisory.设定/力量锚点.yaml")
        assert anchor["status"] == "ok"

    def test_report_carries_schema_and_root(self, v7_book: Path):
        from data_modules.domain_contract import DOMAIN_SCHEMA_VERSION, check_domain_contract

        report = check_domain_contract(v7_book)

        assert report["schema_version"] == DOMAIN_SCHEMA_VERSION
        assert report["project_root"] == str(v7_book)


class TestDoctorWiring:
    def test_doctor_includes_domain_contract_group(self, v7_book: Path, monkeypatch):
        # doctor 需要 .webnovel/state.json 才能解析 phase —— 构造最小 v6+域混合书
        import json

        (v7_book / ".webnovel").mkdir(exist_ok=True)
        (v7_book / ".webnovel" / "state.json").write_text(
            json.dumps({"project_info": {"title": "t"}, "current_chapter": 0}, ensure_ascii=False),
            encoding="utf-8",
        )

        from data_modules.domain_contract import init_domain_skeleton
        from data_modules.doctor import build_doctor_report

        init_domain_skeleton(v7_book)
        report = build_doctor_report(str(v7_book))
        ids = [c["id"] for c in report["checks"]]
        assert any(i.startswith("domains.") for i in ids), "doctor 应包含六域契约检查组"
