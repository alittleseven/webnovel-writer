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


def test_fix_argv_mojibake_false_positive_class_is_real():
    # B-fix 记录误报类：钱平 的 GBK 编码（C7AE C6BD）恰好是合法 UTF-8，
    # 函数会把它改写成乱码——这正是 _fix_sys_argv 默认必须关闭的原因。
    assert _fix_argv_mojibake("钱平") != "钱平"


def test_fix_sys_argv_gated_off_by_default(monkeypatch):
    import sys

    from runtime_compat import _fix_sys_argv

    monkeypatch.setattr(sys, "argv", ["webnovel.py", "--alias", "钱平"])
    monkeypatch.delenv("WEBNOVEL_FIX_ARGV_MOJIBAKE", raising=False)
    _fix_sys_argv()
    assert sys.argv == ["webnovel.py", "--alias", "钱平"]


def test_fix_sys_argv_opt_in_repairs_powershell_mojibake(monkeypatch):
    import sys

    from runtime_compat import _fix_sys_argv

    monkeypatch.setattr(sys, "argv", ["webnovel.py", "--query", "榧犵帇"])
    monkeypatch.setenv("WEBNOVEL_FIX_ARGV_MOJIBAKE", "1")
    _fix_sys_argv()
    assert sys.argv[2] == "鼠王"


def test_fix_sys_argv_opt_in_accepts_true_variants(monkeypatch):
    import sys

    from runtime_compat import _fix_sys_argv

    for value in ("true", "yes", "on", "TRUE"):
        monkeypatch.setenv("WEBNOVEL_FIX_ARGV_MOJIBAKE", value)
        monkeypatch.setattr(sys, "argv", ["webnovel.py", "--query", "钀х値"])
        _fix_sys_argv()
        assert sys.argv[2] == "萧炎", f"env={value} 应开启修复"
