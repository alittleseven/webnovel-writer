#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T4（M0）session_start hook 接线测试（webnovel-copilot-300 F-01）。"""

from __future__ import annotations

from pathlib import Path


def _load_hook():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "session_start_hook", Path(__file__).resolve().parents[2] / "hooks" / "session_start.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestComposeHookOutput:
    def test_sync_brief_comes_first(self):
        hook = _load_hook()
        out = hook.compose_hook_output("项目状态：第 39 章", "作者已改 1 处……")
        assert out.startswith("作者已改")

    def test_empty_parts_dropped(self):
        hook = _load_hook()
        assert hook.compose_hook_output("状态行", "") == "状态行"
        assert hook.compose_hook_output("", "") == ""

    def test_long_status_clipped(self):
        hook = _load_hook()
        out = hook.compose_hook_output("行\n" * 50, "")
        assert len(out.splitlines()) <= hook.MAX_LINES
