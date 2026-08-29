#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Runtime compatibility helpers.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Union


def _fix_argv_mojibake(value: str) -> str:
    """修复 Windows 下 PowerShell 传参时「UTF-8 字节被 GBK 误解码」产生的乱码。

    现象：PowerShell 调用 `python script.py "鼠王"` 时，sys.argv 里可能变成
    「榧犵帇」这类乱码（UTF-8 字节被按 GBK 解读）。修复方式是把字符串按 GBK
    编码还原成原始字节，再按 UTF-8 解码。

    安全性：只有当「GBK 编码 → UTF-8 解码」能无损往返、且结果与原串不同
    时才修复；纯 ASCII、正常中文、路径、参数名等不受影响。
    """
    if not value:
        return value
    try:
        raw = value.encode("gbk")
    except UnicodeEncodeError:
        return value
    try:
        fixed = raw.decode("utf-8")
    except UnicodeDecodeError:
        return value
    if fixed == value or "\ufffd" in fixed:
        return value
    return fixed


def _fix_sys_argv() -> None:
    """就地修复 sys.argv 中的乱码参数（仅 Windows，需 WEBNOVEL_FIX_ARGV_MOJIBAKE=1 显式开启）。

    B-fix：真书实测发现该启发式存在不可消除的误报——「钱平」等正常中文的 GBK
    编码（C7AE C6BD）恰好是合法 UTF-8，会被误判为乱码改写成「Ǯƽ」，导致
    get-by-alias 等中文参数查询失败（fantasy01 第 35 章实测，2026-08-30）。
    真乱码（UTF-8 字节被 GBK 误解码）与正常中文在字符串层面按 GBK/UTF-8 互转
    是对称可逆的，无法可靠区分，故默认不修改 argv；受 PowerShell 传参乱码影响
    的环境可设 WEBNOVEL_FIX_ARGV_MOJIBAKE=1（true/yes/on 亦可）显式开启。
    """
    if sys.platform != "win32":
        return
    flag = os.environ.get("WEBNOVEL_FIX_ARGV_MOJIBAKE", "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return
    try:
        sys.argv = [_fix_argv_mojibake(a) for a in sys.argv]
    except Exception:
        pass


def enable_windows_utf8_stdio(*, skip_in_pytest: bool = False) -> bool:
    """Enable UTF-8 stdio wrappers and fix argv mojibake on Windows.

    Returns:
        True if any wrapping/fix was applied, False otherwise.
    """
    if sys.platform != "win32":
        return False
    if skip_in_pytest and os.environ.get("PYTEST_CURRENT_TEST"):
        return False

    # 修复 sys.argv 中因 PowerShell 传参编码导致的乱码（与 stdio 编码相互独立）
    _fix_sys_argv()

    stdout_encoding = str(getattr(sys.stdout, "encoding", "") or "").lower()
    stderr_encoding = str(getattr(sys.stderr, "encoding", "") or "").lower()
    if stdout_encoding == "utf-8" and stderr_encoding == "utf-8":
        return False

    try:
        import io

        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
        return True
    except Exception:
        return False


_WIN_POSIX_DRIVE_RE = re.compile(r"^/(?P<drive>[a-zA-Z])/(?P<rest>.*)$")
_WIN_WSL_MNT_DRIVE_RE = re.compile(r"^/mnt/(?P<drive>[a-zA-Z])/(?P<rest>.*)$")


def normalize_windows_path(value: Union[str, Path]) -> Path:
    """
    将 Windows 上常见的 POSIX 风格路径规范化为 Windows 盘符路径。

    典型来源：
    - Git Bash / MSYS:  /d/desktop/...  => D:/desktop/...
    - WSL:             /mnt/d/desktop/... => D:/desktop/...

    非 Windows 平台直接返回 Path(value)。
    """
    if sys.platform != "win32":
        return Path(value)

    raw = str(value).strip()
    if not raw:
        return Path(raw)

    m = _WIN_WSL_MNT_DRIVE_RE.match(raw)
    if m:
        drive = m.group("drive").upper()
        rest = m.group("rest")
        return Path(f"{drive}:/{rest}")

    m = _WIN_POSIX_DRIVE_RE.match(raw)
    if m:
        drive = m.group("drive").upper()
        rest = m.group("rest")
        return Path(f"{drive}:/{rest}")

    return Path(value)

