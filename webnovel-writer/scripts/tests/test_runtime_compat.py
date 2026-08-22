# -*- coding: utf-8 -*-
"""runtime_compat 单元测试，重点覆盖 Windows argv 乱码修复。"""
import pytest

from runtime_compat import _fix_argv_mojibake


@pytest.mark.parametrize(
    "raw, expected",
    [
        # 正常中文：不应被改动
        ("鼠王 晶核 仓库", "鼠王 晶核 仓库"),
        ("萧炎", "萧炎"),
        # 纯 ASCII：不应被改动
        ("hello world", "hello world"),
        ("--project-root", "--project-root"),
        # 数字/下划线：不应被改动
        ("chapter_017", "chapter_017"),
        # Windows 路径：不应被改动
        (r"C:\lgq\workspace\path", r"C:\lgq\workspace\path"),
        # 空串：不变
        ("", ""),
        # GBK 误解码的 UTF-8 乱码：应还原为正确中文
        ("榧犵帇 鏅舵牳 浠撳簱", "鼠王 晶核 仓库"),
        ("钀х値", "萧炎"),
    ],
)
def test_fix_argv_mojibake(raw, expected):
    assert _fix_argv_mojibake(raw) == expected


def test_fix_argv_mojibake_does_not_mutate_plain_ascii():
    # 纯 ASCII 往返后与自身相同，不应被改动
    s = "claude plugin install webnovel-writer"
    assert _fix_argv_mojibake(s) == s


def test_fix_argv_mojibake_handles_mixed():
    # 含路径 + 中文乱码混合场景：路径保持，乱码部分还原
    raw = r"C:\books" + " 钀х値"
    fixed = _fix_argv_mojibake(raw)
    assert fixed.startswith(r"C:\books")
    assert "萧炎" in fixed
