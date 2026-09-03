#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


MAX_LINES = 8
MAX_CHARS = 1000
DISABLE_ENV = "WEBNOVEL_DISABLE_SESSION_STATUS_HOOK"


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clip(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()][:MAX_LINES]
    clipped = "\n".join(lines).strip()
    if len(clipped) > MAX_CHARS:
        clipped = clipped[: MAX_CHARS - 3].rstrip() + "..."
    return clipped


def _run_webnovel(webnovel: Path, workspace_root: str, *args: str, timeout: int = 4) -> str:
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(webnovel), "--project-root", workspace_root, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except Exception:
        return ""
    return proc.stdout or proc.stderr or ""


def compose_hook_output(status_text: str, sync_brief: str) -> str:
    """会话注入内容 = 作者修改摘要（若有）+ 项目状态（clip 各自独立，总量有界）。"""
    parts = [part for part in (sync_brief.strip(), _clip(status_text)) if part]
    return "\n".join(parts)


def main() -> int:
    if _truthy(os.environ.get(DISABLE_ENV)):
        return 0

    plugin_root = Path(os.environ.get("ZCODE_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[1])
    workspace_root = os.environ.get("ZCODE_PROJECT_DIR") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    webnovel = plugin_root / "scripts" / "webnovel.py"
    if not webnovel.is_file():
        return 0

    # T4（webnovel-copilot-300 M0）：author-sync 留账 + 作者影响摘要（best-effort）
    sync_brief = _run_webnovel(webnovel, workspace_root, "author-sync", "--format", "text", timeout=6)

    status_text = _run_webnovel(
        webnovel,
        workspace_root,
        "project-status",
        "--format",
        "summary",
    )

    output = compose_hook_output(status_text, sync_brief)
    if output:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
