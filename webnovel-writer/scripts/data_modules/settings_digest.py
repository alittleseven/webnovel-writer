#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""settings_digest — 设定集 L0 摘要层（S3/C3）。

L0：每个设定文件一份 ~240 字符的确定性结构摘要（主题行 + ## 骨架 + 首个要点），
落盘 `.webnovel/settings_digest/{keyword}.json`（含源文件 sha256）。
L2：原文按需经 `setting-read` 命令或 Read 展开给 agent。

摘要自动维护：源文件 sha256 与记录不一致即就地重建，无需依赖 init/plan 重跑；
非 ZCode/无设定文件时返回空串，调用方回退旧路径。
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional

DIGEST_DIR_NAME = "settings_digest"
DEFAULT_DIGEST_MAX_CHARS = 240
_TRUNCATION_MARK = "…（L0 截断）"


def digest_dir(config: Any) -> Path:
    return config.webnovel_dir / DIGEST_DIR_NAME


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_digest(text: str, max_chars: int = DEFAULT_DIGEST_MAX_CHARS) -> str:
    """确定性 L0 摘要：主题行｜## 骨架｜首个要点行，超长截断。"""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = next((ln.lstrip("# ").strip() for ln in lines if ln.startswith("# ")), "")
    subtitles = [ln.lstrip("# ").strip() for ln in lines if ln.startswith("## ")]
    first_point = next((ln for ln in lines if ln and not ln.startswith("#")), "")

    parts = [title, "；".join(subtitles[:12]), first_point]
    out_parts: list[str] = []
    used = 0
    for part in parts:
        if not part:
            continue
        remaining = max_chars - len(_TRUNCATION_MARK) - used - (1 if used else 0)
        if len(part) <= remaining:
            out_parts.append(part)
            used += len(part) + (1 if used else 0)
            continue
        # 放不下：截断该段并结束（保序不保全部）
        if remaining > 0:
            out_parts.append(part[:remaining] + _TRUNCATION_MARK)
        break
    out = "｜".join(out_parts) if out_parts else text[: max(0, max_chars)]
    if len(out) > max_chars:
        out = out[: max(0, max_chars - len(_TRUNCATION_MARK))] + _TRUNCATION_MARK
    return out


def _find_setting_path(settings_dir: Path, keyword: str) -> Optional[Path]:
    exact = settings_dir / f"{keyword}.md"
    if exact.exists():
        return exact
    matches = sorted(settings_dir.glob(f"*{keyword}*.md"))
    return matches[0] if matches else None


def get_setting_digest(config: Any, keyword: str, settings_dir: Optional[Path] = None) -> str:
    """返回 keyword 设定文件的 L0 摘要（自动构建/陈旧自愈）；无源文件返回空串。"""
    settings_dir = Path(settings_dir) if settings_dir else config.settings_dir
    source = _find_setting_path(settings_dir, keyword)
    if source is None:
        return ""
    try:
        text = source.read_text(encoding="utf-8")
    except OSError:
        return ""
    if not text.strip():
        return ""

    sha = _sha256(text)
    ddir = digest_dir(config)
    ddir.mkdir(parents=True, exist_ok=True)
    record_path = ddir / f"{keyword}.json"
    if record_path.exists():
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record.get("source_sha256") == sha and record.get("digest"):
                return str(record["digest"])
        except (json.JSONDecodeError, OSError):
            pass

    max_chars = int(getattr(config, "context_settings_digest_max_chars", DEFAULT_DIGEST_MAX_CHARS) or DEFAULT_DIGEST_MAX_CHARS)
    digest = build_digest(text, max_chars=max_chars)
    record: dict[str, Any] = {
        "keyword": keyword,
        "source_sha256": sha,
        "digest": digest,
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return digest
