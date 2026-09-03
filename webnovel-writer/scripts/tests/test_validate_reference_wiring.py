#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T27（M5）validate_reference_wiring 引用对账测试（R15/F-19）。

契约：三类漂移（orphan 孤儿未登记 / unwired 登记未接线 / missing 引用缺失）
全部被报出；显式退役合法；代码消费目录（templates/genres 等）豁免 orphan；
清零时退出码 0。
"""

from __future__ import annotations

import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def _make_plugin(tmp_path: Path):
    """最小插件树：SKILL + loading-map + 三个不同状态的资产。"""
    root = tmp_path / "plugin"
    skill_dir = root / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    refs = root / "references" / "shared"
    refs.mkdir(parents=True)
    genres = root / "templates" / "genres"
    genres.mkdir(parents=True)

    # wired：被 SKILL 引用
    (refs / "wired.md").write_text("已接线资产", encoding="utf-8")
    # orphan：存在、无人引用、未登记
    (refs / "orphan.md").write_text("孤儿资产", encoding="utf-8")
    # retired：存在、无人引用、loading-map 显式退役
    (refs / "retired.md").write_text("退役资产", encoding="utf-8")
    # 代码消费目录：无引用也不算 orphan
    (genres / "系统流.md").write_text("题材模板", encoding="utf-8")
    # missing：SKILL 引用但文件不存在
    (skill_dir / "SKILL.md").write_text(
        "读 `references/shared/wired.md`；读 `references/shared/ghost.md`。\n",
        encoding="utf-8",
    )
    (root / "references" / "index").mkdir(parents=True)
    (root / "references" / "index" / "reference-loading-map.md").write_text(
        "| demo | Step 1 | always | `references/shared/wired.md` | 全文 |\n"
        "| 退役登记：`references/shared/retired.md` 已删除 |\n",
        encoding="utf-8",
    )
    return root


def test_three_drift_kinds_detected(tmp_path: Path):
    from validate_reference_wiring import build_report

    root = _make_plugin(tmp_path)
    report = build_report(root)

    kinds = {item["path"]: item["kind"] for item in report["drift"]}
    assert kinds.get("references/shared/orphan.md") == "orphan", "孤儿未登记被报出"
    assert kinds.get("references/shared/ghost.md") == "missing", "引用缺失被报出"
    assert report["ok"] is False


def test_wired_and_retired_and_code_consumed_clean(tmp_path: Path):
    from validate_reference_wiring import build_report

    root = _make_plugin(tmp_path)
    report = build_report(root)

    paths = {item["path"] for item in report["drift"]}
    assert "references/shared/wired.md" not in paths, "已接线资产不报"
    assert "references/shared/retired.md" not in paths, "显式退役合法"
    assert "templates/genres/系统流.md" not in paths, "代码消费目录豁免 orphan"


def test_clean_tree_exits_ok(tmp_path: Path):
    from validate_reference_wiring import build_report, main

    root = _make_plugin(tmp_path)
    # 修掉仅有的两类漂移 → 清零
    (root / "references" / "shared" / "orphan.md").unlink()
    (root / "skills" / "demo" / "references-shared").mkdir()
    (root / "references" / "shared" / "ghost.md").write_text("补上", encoding="utf-8")

    report = build_report(root)

    assert report["ok"] is True
    assert report["drift_count"] == 0
    assert main(["--root", str(root)]) == 0
