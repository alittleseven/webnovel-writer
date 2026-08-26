#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows 长路径只读原语（单一事实源）。

在未开启系统 LongPathsEnabled 的 Windows 上，超过 MAX_PATH(260) 字符的路径
会让 isfile/stat/open 等 Win32 调用以 ENOENT 或拒绝访问失败。中文书名 +
深层项目目录很容易触发。本模块统一提供扩展前缀（\\?\）转换与常用的
只读原语，供原子写入（security_utils）、运行账本、章节定位和 dashboard 复用；
短路径行为完全不变。
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Iterator, Optional, Sequence, Union

WIN_EXTENDED_PREFIX = "\\\\?\\"
_LONG_PATH_THRESHOLD = 200


def win_long_abs(path: Union[str, "os.PathLike[str]"]) -> str:
    """绝对化路径；Windows 上接近 MAX_PATH 时加扩展前缀保证可用。

    阈值取 200：目录之后通常还要拼接临时文件名或前后缀（约 30-40 字符），
    必须在目录阶段预留增长空间。
    """
    s = str(path)
    if not s.startswith(WIN_EXTENDED_PREFIX):
        s = os.path.abspath(s)
    if os.name == "nt" and len(s) >= _LONG_PATH_THRESHOLD and not s.startswith(WIN_EXTENDED_PREFIX):
        s = WIN_EXTENDED_PREFIX + s
    return s


def is_file(path: Union[str, "os.PathLike[str]"]) -> bool:
    return os.path.isfile(win_long_abs(path))


def is_dir(path: Union[str, "os.PathLike[str]"]) -> bool:
    return os.path.isdir(win_long_abs(path))


def mtime_ns(path: Union[str, "os.PathLike[str]"]) -> Optional[int]:
    try:
        return os.stat(win_long_abs(path)).st_mtime_ns
    except OSError:
        return None


def file_size(path: Union[str, "os.PathLike[str]"]) -> Optional[int]:
    try:
        return os.stat(win_long_abs(path)).st_size
    except OSError:
        return None


def read_bytes(path: Union[str, "os.PathLike[str]"]) -> bytes:
    with open(win_long_abs(path), "rb") as handle:
        return handle.read()


def read_text(path: Union[str, "os.PathLike[str]"], *, encoding: str = "utf-8") -> str:
    with open(win_long_abs(path), "r", encoding=encoding) as handle:
        return handle.read()


def iter_files(base: Union[str, "os.PathLike[str]"], patterns: Sequence[str]) -> Iterator[Path]:
    """在 base 下递归匹配 patterns 的文件，目录遍历本身走扩展前缀。

    pathlib 的 rglob/scandir 在子目录路径超过 MAX_PATH 时会抛 ENOENT，
    这里改用 os.scandir(win_long_abs(...)) 逐层扫描；无法进入的分支静默跳过。
    返回顺序不保证，调用方需要排序。
    """
    pats = tuple(patterns)
    stack: list[Path] = [Path(base)]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(win_long_abs(current)))
        except OSError:
            continue
        for entry in entries:
            child = current / entry.name
            try:
                if entry.is_file():
                    if any(fnmatch.fnmatch(entry.name, pattern) for pattern in pats):
                        yield child
                elif entry.is_dir():
                    stack.append(child)
            except OSError:
                continue
