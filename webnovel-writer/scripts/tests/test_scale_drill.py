#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T33（M7）规模演练测试（CI 用小规模；300 章全量由脚本手动跑）。

对应方案：01 §6 成功标准 5、08 T33。
契约：run_drill 合成书仓 → 治理全链（timeline build/check、伏笔扫描、素材装配/
校验、对账）全部成功、逾期检出、装配十表、单步与总耗时在预算内。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


@pytest.fixture(scope="module")
def drill(tmp_path_factory):
    from data_modules.scale_drill import run_drill

    workdir = tmp_path_factory.mktemp("drill")
    return run_drill(chapters=40, workdir=workdir)


def test_drill_passes(drill):
    assert drill["ok"] is True, drill["correct"]


def test_drill_overdue_detected(drill):
    assert drill["overdue_detected_count"] > 0, "合成的逾期条目必须被扫描器全数捕获"


def test_drill_assemble_covers_all_tables(drill):
    assert drill["correct"]["assemble_tables"] is True


def test_drill_steps_within_budget(drill):
    for step in drill["steps"]:
        assert step["within_budget"], f"{step['step']} 超出单步预算：{step['seconds']}s"
    assert drill["within_budget"] is True
