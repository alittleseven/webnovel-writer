#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows 长路径只读原语与核心读取触点回归。"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import long_paths  # noqa: E402
from chapter_paths import find_chapter_file  # noqa: E402
from data_modules.run_ledger import file_signature  # noqa: E402


def _make_deep_file(base_dir: Path, rel_parts: tuple[str, ...], content: bytes) -> Path:
    """在 base_dir 下按 rel_parts 创建超长路径文件，返回未加前缀的 Path。"""
    target = base_dir.joinpath(*rel_parts)
    while len(str(target)) < 262:
        target = target.parent / ("d" * 40) / target.name
    assert len(str(target)) > 260
    prefixed_parent = long_paths.win_long_abs(target.parent)
    os.makedirs(prefixed_parent, exist_ok=True)
    with open(long_paths.win_long_abs(target), "wb") as handle:
        handle.write(content)
    return target


def test_win_long_abs_keeps_short_paths_plain(tmp_path: Path) -> None:
    short = tmp_path / "state.json"
    converted = long_paths.win_long_abs(short)
    if os.name == "nt":
        # 短路径仅做绝对化，不加扩展前缀
        assert not converted.startswith(long_paths.WIN_EXTENDED_PREFIX)
    assert os.path.isabs(converted)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 扩展前缀行为")
def test_win_long_abs_prefixes_long_paths() -> None:
    raw = "C:\\" + ("d" * 40 + "\\") * 5 + "f.json"
    assert len(raw) >= 200
    converted = long_paths.win_long_abs(raw)
    assert converted.startswith("\\\\?\\")


def test_read_primitives_roundtrip_normal_path(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b.txt"
    target.parent.mkdir(parents=True)
    target.write_bytes("正文\n".encode("utf-8"))

    assert long_paths.is_file(target) is True
    assert long_paths.file_size(target) == len("正文\n".encode("utf-8"))
    assert isinstance(long_paths.mtime_ns(target), int)
    assert long_paths.read_bytes(target) == "正文\n".encode("utf-8")
    assert long_paths.read_text(target) == "正文\n"
    assert long_paths.is_dir(target.parent) is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows MAX_PATH 回归场景")
def test_deep_paths_visible_to_core_read_touchpoints(tmp_path: Path) -> None:
    """>260 字符路径下 file_signature 与 find_chapter_file 必须照常工作。

    复现：书项目放在深层目录时，正文 sha256 校验静默报“不存在”、
    find_chapter_file 直接抛 FileNotFoundError。
    """
    content = "第0001章 正文内容\n".encode("utf-8")
    chapter_rel = ("正文", "第0001章.md")

    project_root = tmp_path
    deep_chapter = _make_deep_file(project_root, chapter_rel, content)

    # 触点一：run_ledger.file_signature 能看到超长路径文件并算出正确哈希
    signature = file_signature(deep_chapter)
    assert signature["exists"] is True
    assert signature["size"] == len(content)
    assert signature["sha256"] == hashlib.sha256(content).hexdigest()

    # 触点二：find_chapter_file 在深层目录能定位本章
    found = find_chapter_file(project_root, 1)
    assert found is not None and found.name == "第0001章.md"

    # 触点三：long_paths 原语本身对深路径可用
    assert long_paths.read_bytes(deep_chapter) == content
    assert long_paths.mtime_ns(deep_chapter) is not None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows MAX_PATH 回归场景")
def test_find_chapter_file_survives_unscannable_depth_without_crash(tmp_path: Path) -> None:
    """rglob 遇到无法扫描的深层目录时应优雅跳过，而不是抛异常中断流程。"""
    (tmp_path / "正文").mkdir(parents=True)
    normal = tmp_path / "正文" / "第0002章.md"
    normal.write_text("第0002章\n", encoding="utf-8")

    deep_dir = tmp_path / "正文"
    while len(str(deep_dir / "x.md")) < 262:
        deep_dir = deep_dir / ("d" * 40)
    try:
        os.makedirs(long_paths.win_long_abs(deep_dir), exist_ok=True)
    except OSError as exc:  # 某些环境可能限制创建深度；此时验证当前层即可
        pytest.skip(f"无法构造更深目录: {exc}")

    found = find_chapter_file(tmp_path, 2)
    assert found is not None and found.name == "第0002章.md"
