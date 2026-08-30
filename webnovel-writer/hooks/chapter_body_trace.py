#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chapter_body_trace — 正文目录 PostToolUse 留痕钩子（S8/P2-6）。

P2-6 定位：作者是所有者，正文可手改；本钩子只记录「哪个工具动了正文哪个文件」
到 `.webnovel/logs/chapter_body_trace.log`（JSONL），供 doctor / write-resume
检测手改漂移，不阻断、不校验内容。任何异常静默退出 0。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_BODY_DIR_NAME = "正文"
_LOG_REL = Path(".webnovel") / "logs" / "chapter_body_trace.log"


def resolve_project_root() -> Path | None:
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("ZCODE_PROJECT_DIR")
    candidates = [Path(env_dir)] if env_dir else []
    candidates.append(Path.cwd())
    for candidate in candidates:
        if candidate and (candidate / ".webnovel" / "state.json").is_file():
            return candidate
    return None


def record_edit(project_root: Path, tool: str, file_path: str) -> bool:
    """正文/ 目录下的写入留痕；返回是否记录。"""
    try:
        target = Path(file_path).resolve()
        body_dir = (Path(project_root) / _BODY_DIR_NAME).resolve()
    except OSError:
        return False
    if body_dir not in target.parents:
        return False
    log_path = Path(project_root) / _LOG_REL
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tool": str(tool or ""),
        "path": str(target),
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return True


def main() -> int:
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        payload = json.loads(raw or "{}")
    except Exception:
        return 0
    try:
        root = resolve_project_root()
        if root is None:
            return 0
        tool_input = payload.get("tool_input") or {}
        file_path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        if file_path:
            record_edit(root, str(payload.get("tool_name") or ""), file_path)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
