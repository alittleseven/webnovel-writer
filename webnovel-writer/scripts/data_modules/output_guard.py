#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""output_guard — 统一 CLI 大输出外置化（S10/D3）。

对标 OpenViking tool_output externalization：进程内命令的 stdout 超过阈值时，
全文落盘 `<root>/.webnovel/tmp/cli_out/<tool>.txt`（同名覆盖，路径可预测），
对话只留摘要存根（前 600 字符预览 + 引用路径）。

豁免：`_run_script` 子进程转发类命令（extract-context / memory-contract /
story-system 等）不经此通道——它们在 S1-S9 已是紧凑输出；环境变量
`WEBNOVEL_OUTPUT_EXTERNALIZE=0` 可整体关闭，`WEBNOVEL_OUTPUT_EXTERNALIZE_CHARS`
可调阈值（默认 20000 字符）。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

OUTPUT_EXTERNALIZE_CHARS = 20000
_HEAD_PREVIEW_CHARS = 600
_STUB_MARK = "EXTERNALIZED"


def _disabled() -> bool:
    return os.environ.get("WEBNOVEL_OUTPUT_EXTERNALIZE", "").strip().lower() in {"0", "false", "off"}


def _threshold() -> int:
    raw = os.environ.get("WEBNOVEL_OUTPUT_EXTERNALIZE_CHARS", "").strip()
    try:
        value = int(raw)
    except ValueError:
        return OUTPUT_EXTERNALIZE_CHARS
    return value if value > 0 else OUTPUT_EXTERNALIZE_CHARS


def externalize_if_needed(
    output: str,
    *,
    tool: str,
    project_root: Optional[Path],
) -> str:
    """超过阈值的外置化：全文落盘 + 摘要存根；否则原样返回。"""
    if _disabled() or not output:
        return output
    threshold = _threshold()
    if len(output) <= threshold or project_root is None:
        return output

    dump_dir = Path(project_root) / ".webnovel" / "tmp" / "cli_out"
    try:
        dump_dir.mkdir(parents=True, exist_ok=True)
        dump_path = dump_dir / f"{tool or 'cli'}.txt"
        dump_path.write_text(output, encoding="utf-8")
    except OSError:
        return output

    head = output[:_HEAD_PREVIEW_CHARS]
    return (
        f"{_STUB_MARK} cli-output tool=\"{tool or 'cli'}\" chars={len(output)} "
        f"threshold={threshold}\n"
        f"head:\n{head}\n"
        f"full-output: {dump_path}"
    )
