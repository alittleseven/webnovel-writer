#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UserPromptSubmit 钩子：写章进行中注入「本章累计」token 消耗（D1b）。

数据源与口径同 data_modules/chapter_meter（只读 ZCode 本地用量库）。
计量标记 ``.webnovel/tmp/chapter_meter.json`` 存在且 open 时，输出
``{"additionalContext": "【本章累计】..."}`` 到 stdout；否则静默退出 0。
任何异常都静默退出 0，绝不阻塞用户输入。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_scripts = str(_PLUGIN_ROOT / "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from data_modules.chapter_meter import aggregate_usage, read_marker  # noqa: E402


def _has_state(path: Path) -> bool:
    try:
        return (path / ".webnovel" / "state.json").is_file()
    except OSError:
        return False


def resolve_project_root() -> Path | None:
    """CLAUDE_PROJECT_DIR → cwd 向上 → 全局指针文件，取第一个含 state.json 的目录。"""
    candidates: list[Path] = []
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("ZCODE_PROJECT_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(Path.cwd())
    pointer = Path.home() / ".claude" / ".webnovel-current-project"
    if pointer.is_file():
        try:
            target = pointer.read_text(encoding="utf-8").strip()
            if target:
                candidates.append(Path(target))
        except OSError:
            pass
    for candidate in candidates:
        if candidate and _has_state(candidate):
            return candidate
    return None


def get_session_id() -> str:
    if "--session" in sys.argv:
        i = sys.argv.index("--session")
        if i + 1 < len(sys.argv):
            sid = sys.argv[i + 1]
            if sid and not sid.startswith("${"):
                return sid
    sid = os.environ.get("CLAUDE_SESSION_ID", "")
    return "" if sid.startswith("${") else sid


def build_message(project_root: Path, session_hint: str = "", db_path: Path | None = None) -> str | None:
    marker = read_marker(project_root)
    if not marker or marker.get("status") != "open":
        return None
    if session_hint and not marker.get("session_id"):
        marker = {**marker, "session_id": session_hint}
    usage = aggregate_usage(Path(project_root), marker, db_path=db_path)
    if usage.get("usage_db_missing") or usage["requests"] == 0:
        return None
    return (
        f"【本章累计】第{marker.get('chapter')}章：请求 {usage['requests']} 次"
        f" | 输入 {usage['input']:,}（缓存读 {usage['cache_read']:,}）"
        f" | 输出 {usage['output']:,} | 总计 {usage['total']:,} tokens（含子代理）"
        f" | 新增 {usage['new_tokens']:,}"
    )


def main() -> int:
    try:
        root = resolve_project_root()
        if root is None:
            return 0
        msg = build_message(root, session_hint=get_session_id())
        if msg:
            print(json.dumps({"additionalContext": msg}, ensure_ascii=False))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
