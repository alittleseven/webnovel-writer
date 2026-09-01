#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dual_format_guard — v6/v7 双格式期间的唯一写入路径守卫（S18/E4）。

不变量：同一章节在双格式期间只允许一种格式落定，禁止双写。
- v6 落定 = `.story-system/commits/chapter_NNN.commit.json` 且 meta.status == "accepted"
- v7 落定 = `<story_repo_root>/定稿/正文/NNNN-标题.md`（story-repo spec 0.4 §4.1，仅由 settle 写出）

v7 仓库根经配置 `story_repo_root` 提供（S16 迁移器建立映射后填入）；
缺省为空 = v7 侧不存在，守卫对既有 v6 项目零行为变化。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .write_gates import issue

V7_FINALIZED_DIR = Path("定稿") / "正文"


def has_v6_accepted_chapter(project_root: Path, chapter: int) -> bool:
    commit_path = Path(project_root) / ".story-system" / "commits" / f"chapter_{int(chapter):03d}.commit.json"
    if not commit_path.exists():
        return False
    try:
        payload = json.loads(commit_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return ((payload.get("meta") or {}).get("status")) == "accepted"


def has_v7_settled_chapter(story_repo_root: Optional[Path | str], chapter: int) -> bool:
    if not story_repo_root:
        return False
    final_dir = Path(story_repo_root) / V7_FINALIZED_DIR
    if not final_dir.is_dir():
        return False
    prefix = f"{int(chapter):04d}-"
    return any(p.name.startswith(prefix) and p.suffix == ".md" for p in final_dir.iterdir())


def detect_chapter_formats(
    project_root: Path,
    chapter: int,
    story_repo_root: Optional[Path | str] = None,
) -> dict[str, Any]:
    return {
        "v6": has_v6_accepted_chapter(Path(project_root), chapter),
        "v7": has_v7_settled_chapter(story_repo_root, chapter),
        "story_repo_root": str(story_repo_root) if story_repo_root else "",
    }


def check_unique_write_path(
    project_root: Path,
    chapter: int,
    *,
    target_format: str,
    story_repo_root: Optional[Path | str] = None,
) -> Optional[dict[str, Any]]:
    """目标格式写入前的唯一性检查：另一格式已落定该章 → 返回 blocker issue，否则 None。"""
    if target_format not in {"v6", "v7"}:
        raise ValueError(f"unknown target_format: {target_format}")
    formats = detect_chapter_formats(project_root, chapter, story_repo_root=story_repo_root)
    other = "v7" if target_format == "v6" else "v6"
    if not formats.get(other):
        return None
    return issue(
        "dual_format_write_blocked",
        message=f"第 {chapter} 章已以 {other} 格式落定，禁止以 {target_format} 双写",
        impact="同一章节双写会造成两套事实源分叉，破坏唯一写入路径不变量。",
        repair=(
            f"以已落定的 {other} 格式为准继续工作；确需改写时走显式迁移/retcon 事务，"
            "并在另一格式中撤销该章的落定记录。"
        ),
        details={"chapter": int(chapter), "settled_format": other, **formats},
    )
