#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T20（M4）设定工坊四生成器测试（提案模式）。

对应方案：07 F-08（输入装配 → 5 组提案 → 画廊 → 采纳草案 → 登记三处同步 →
采纳率入 signals）、08 T20。
红线契约：①提案不得出现战力数值（正则检出即拒绝）；②境界/功法类提案必须带
「灵魂设定——建议作者自拟，工坊仅给反差参考」标注；③一批必须恰 5 组提案；
④采纳后扩写草案仍走画廊二次确认，confirm 才三处同步（设定 md + 锚点同步标记 +
合同重编译标记）并写采纳率 signals。
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _proposal_doc(category: str, *, count: int = 5, annotation: bool = True, numeric: bool = False) -> str:
    lines = [f"# {category}提案（5 组概念组合）", ""]
    for index in range(1, count + 1):
        lines.extend(
            [
                f"## 提案 {index}",
                f"- 概念拼接：{category}概念{index} × 灾厄残响",
                f"- 反差钩子：越用越弱的反向成长{index}",
                f"- 差异点：与既有设定错开{index}",
                "- 常见度自评：低",
                "",
            ]
        )
    if numeric:
        lines.append("- 战力值：99999")
    if annotation:
        lines.append("灵魂设定——建议作者自拟，工坊仅给反差参考")
    return "\n".join(lines) + "\n"


@pytest.fixture()
def book(tmp_path: Path) -> Path:
    from data_modules.author_model import write_preferences
    from data_modules.domain_contract import init_domain_skeleton
    from data_modules.material_store import append_entries

    init_domain_skeleton(tmp_path)
    (tmp_path / "定稿" / "设定").mkdir(parents=True, exist_ok=True)
    append_entries(tmp_path, "金手指零件", [{"id": "GF-001", "名称": "代价转化", "核心摘要": "吃灾转化"}])
    write_preferences(tmp_path, {"节奏": {"冲突前置": True}, "雷点": ["无代价金手指"], "审稿习惯": {}})
    return tmp_path


class TestPrepare:
    def test_prepare_outputs_brief_with_materials_and_taboos(self, book: Path):
        from data_modules.setting_forge import forge_prepare

        report = forge_prepare(book, category="功法")

        assert report["ok"] is True
        brief = report["brief"]
        assert "代价转化" in brief, "装配素材零件"
        assert "无代价金手指" in brief, "装配 author_model 雷点"
        assert "灵魂设定" in brief, "红线提示进装配简报"
        assert report["template"].count("提案") >= 5


class TestSave:
    def test_save_valid_proposals_to_gallery(self, book: Path, tmp_path: Path):
        from data_modules.author_journal import read_journal
        from data_modules.setting_forge import forge_save, list_versions

        proposal_file = tmp_path / "功法提案.md"
        proposal_file.write_text(_proposal_doc("功法"), encoding="utf-8")
        report = forge_save(book, category="功法", file=proposal_file)

        assert report["ok"] is True
        assert report["version"] == 1
        assert list_versions(book, category="功法")[0]["proposals"] == 5
        assert any(e["action"] == "regen" and e["domain"] == "设定" for e in read_journal(book))

    def test_save_rejects_wrong_proposal_count(self, book: Path, tmp_path: Path):
        from data_modules.setting_forge import forge_save

        proposal_file = tmp_path / "few.md"
        proposal_file.write_text(_proposal_doc("功法", count=3), encoding="utf-8")
        report = forge_save(book, category="功法", file=proposal_file)

        assert report["ok"] is False
        assert report["error"] == "proposal_count"

    def test_save_rejects_numeric_power(self, book: Path, tmp_path: Path):
        from data_modules.setting_forge import forge_save

        proposal_file = tmp_path / "numeric.md"
        proposal_file.write_text(_proposal_doc("功法", numeric=True), encoding="utf-8")
        report = forge_save(book, category="功法", file=proposal_file)

        assert report["ok"] is False
        assert report["error"] == "numeric_power_detected", "红线：不出战力数值"

    def test_save_requires_soul_annotation_for_core_categories(self, book: Path, tmp_path: Path):
        from data_modules.setting_forge import forge_save

        proposal_file = tmp_path / "realm.md"
        proposal_file.write_text(_proposal_doc("境界", annotation=False), encoding="utf-8")
        report = forge_save(book, category="境界", file=proposal_file)

        assert report["ok"] is False
        assert report["error"] == "soul_annotation_missing"

    def test_save_artifact_category_needs_no_annotation(self, book: Path, tmp_path: Path):
        from data_modules.setting_forge import forge_save

        proposal_file = tmp_path / "artifact.md"
        proposal_file.write_text(_proposal_doc("法宝", annotation=False), encoding="utf-8")
        report = forge_save(book, category="法宝", file=proposal_file)

        assert report["ok"] is True


class TestAdoptAndConfirm:
    def test_adopt_creates_draft_for_second_confirmation(self, book: Path, tmp_path: Path):
        from data_modules.setting_forge import forge_adopt, forge_save

        proposal_file = tmp_path / "p.md"
        proposal_file.write_text(_proposal_doc("功法"), encoding="utf-8")
        forge_save(book, category="功法", file=proposal_file)

        report = forge_adopt(book, category="功法", version=1, proposal=2)

        assert report["ok"] is True
        assert Path(report["draft"]).is_file(), "采纳=扩写为草案，仍走画廊二次确认"

    def test_confirm_registers_three_way_sync(self, book: Path, tmp_path: Path):
        from data_modules.author_journal import read_journal
        from data_modules.setting_forge import forge_adopt, forge_confirm, forge_save

        proposal_file = tmp_path / "p.md"
        proposal_file.write_text(_proposal_doc("功法"), encoding="utf-8")
        forge_save(book, category="功法", file=proposal_file)
        adopt = forge_adopt(book, category="功法", version=1, proposal=2)

        report = forge_confirm(book, category="功法", draft=adopt["draft"])

        assert report["ok"] is True
        assert Path(report["registered"]).is_file(), "①设定域登记文件"
        assert report["anchor_sync"] == "required", "②涉战力类：力量锚点同步登记"
        assert report["contract_rebuild"] == "required", "③合同重编译登记"
        events = read_journal(book)
        confirm_event = next(e for e in events if e["action"] == "adopt" and "工坊" in str(e.get("summary")))
        assert any(i.startswith("power_anchor_sync") for i in confirm_event["impact"])
        assert any(i.startswith("contract_rebuild") for i in confirm_event["impact"])

    def test_confirm_appends_adoption_rate_signal(self, book: Path, tmp_path: Path):
        from data_modules.setting_forge import forge_adopt, forge_confirm, forge_save

        proposal_file = tmp_path / "p.md"
        proposal_file.write_text(_proposal_doc("命名"), encoding="utf-8")
        forge_save(book, category="命名", file=proposal_file)
        adopt = forge_adopt(book, category="命名", version=1, proposal=1)
        forge_confirm(book, category="命名", draft=adopt["draft"])

        signals = (book / "演化" / "signals.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert any('"forge_adopt"' in line for line in signals), "采纳率统计入 signals（F-08⑤）"

    def test_confirm_requires_known_draft(self, book: Path):
        from data_modules.setting_forge import forge_confirm

        report = forge_confirm(book, category="功法", draft="不存在.md")
        assert report["ok"] is False
        assert report["error"] == "draft_missing"


class TestCLI:
    def test_cli_prepare_save_adopt_confirm(self, book: Path, tmp_path: Path, capsys):
        from data_modules.setting_forge import main

        proposal_file = tmp_path / "p.md"
        proposal_file.write_text(_proposal_doc("命名"), encoding="utf-8")
        assert main(["prepare", "--category", "命名", "--project-root", str(book)]) == 0
        assert main(["save", "--category", "命名", "--file", str(proposal_file), "--project-root", str(book)]) == 0
        assert main(["adopt", "--category", "命名", "--version", "1", "--proposal", "3", "--project-root", str(book)]) == 0
        out = capsys.readouterr().out
        assert "命名-v1-提案3-草案.md" in out
