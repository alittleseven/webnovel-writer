#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""genre_taxonomy 入口测试（审阅报告 P3：taxonomy 收敛缺入口测试）。

以真实 genre-index.csv 为数据源，锁定两个公开 resolver 的入口行为。
"""
from __future__ import annotations

import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from genre_taxonomy import (  # noqa: E402
    resolve_canonical_genre,
    resolve_genre_input,
    resolve_template_stems,
)


def test_empty_input_passthrough():
    r = resolve_genre_input("")
    assert r.canonical_genre == ""
    assert r.template_files == []
    assert resolve_genre_input(None).canonical_genre == ""


def test_all_keyword_passthrough():
    assert resolve_genre_input("全部").canonical_genre == "全部"


def test_alias_resolves_with_template():
    r = resolve_genre_input("玄幻")
    assert r.canonical_genre == "玄幻"
    assert r.template_files == ["修仙.md"]
    assert resolve_template_stems("玄幻") == ["修仙"]


def test_direct_canonical_and_composite():
    assert resolve_genre_input("都市").canonical_genre == "都市"
    r = resolve_genre_input("都市+科幻")
    assert r.canonical_genre == "都市"
    assert "科幻.md" in r.template_files
    assert r.unresolved == []


def test_unresolved_reported():
    r = resolve_genre_input("完全不存在的题材xx")
    assert r.unresolved == ["完全不存在的题材xx"]
    assert r.canonical_genre is None or r.canonical_genre == ""


def test_resolve_canonical_genre_fallback_keeps_raw():
    assert resolve_canonical_genre("完全不存在的题材xx") == "完全不存在的题材xx"
    assert resolve_canonical_genre("玄幻") == "玄幻"
