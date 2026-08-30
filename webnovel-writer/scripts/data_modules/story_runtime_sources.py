#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from chapter_outline_loader import volume_num_for_chapter_from_state

from .story_contracts import StoryContractPaths, read_json_if_exists


@dataclass
class RuntimeSourceSnapshot:
    chapter: int
    contracts: dict[str, dict[str, Any]]
    latest_commit: dict[str, Any] | None
    latest_accepted_commit: dict[str, Any] | None
    fallback_sources: list[str] = field(default_factory=list)
    primary_write_source: str = "chapter_commit"

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapter": self.chapter,
            "contracts": self.contracts,
            "latest_commit": self.latest_commit,
            "latest_accepted_commit": self.latest_accepted_commit,
            "fallback_sources": list(self.fallback_sources),
            "primary_write_source": self.primary_write_source,
        }


def _volume_for_chapter(project_root: Path, chapter: int) -> int:
    return volume_num_for_chapter_from_state(project_root, chapter) or 1


def _read_pointer(paths: StoryContractPaths) -> dict[str, Any]:
    """S7：latest 指针（persist_commit 维护）。指针语义 = 最大章号；缺失/损坏返回空。"""
    payload = read_json_if_exists(paths.latest_pointer_json())
    return payload if isinstance(payload, dict) else {}


def _load_latest_commit(paths: StoryContractPaths, chapter: int, project_root: Path | None = None) -> dict[str, Any] | None:
    # S7：指针直达（1 <= pointer <= chapter 且文件存在），失效/越界回退线性扫描自愈
    pointer_chapter = int(_read_pointer(paths).get("latest_chapter") or 0)
    if 1 <= pointer_chapter <= chapter:
        payload = read_json_if_exists(paths.commit_json(pointer_chapter))
        if payload:
            return payload
    for current in range(chapter, 0, -1):
        payload = read_json_if_exists(paths.commit_json(current))
        if payload:
            return payload
    return None


def _load_latest_accepted_commit(paths: StoryContractPaths, chapter: int, project_root: Path | None = None) -> dict[str, Any] | None:
    pointer_chapter = int(_read_pointer(paths).get("latest_accepted_chapter") or 0)
    if 1 <= pointer_chapter <= chapter:
        payload = read_json_if_exists(paths.commit_json(pointer_chapter))
        if payload and (payload.get("meta") or {}).get("status") == "accepted":
            return payload
    for current in range(chapter, 0, -1):
        payload = read_json_if_exists(paths.commit_json(current))
        if payload and (payload.get("meta") or {}).get("status") == "accepted":
            return payload
    return None


def load_runtime_sources(project_root: Path, chapter: int) -> RuntimeSourceSnapshot:
    project_root = Path(project_root)
    paths = StoryContractPaths.from_project_root(project_root)
    volume = _volume_for_chapter(project_root, chapter)

    contracts = {
        "master": read_json_if_exists(paths.master_json) or {},
        "volume": read_json_if_exists(paths.volume_json(volume)) or {},
        "chapter": read_json_if_exists(paths.chapter_json(chapter)) or {},
        "review": read_json_if_exists(paths.review_json(chapter)) or {},
    }
    latest_commit = _load_latest_commit(paths, chapter, project_root=project_root)
    latest_accepted_commit = _load_latest_accepted_commit(paths, chapter, project_root=project_root)

    fallback_sources: list[str] = []
    for key, payload in contracts.items():
        if not payload:
            fallback_sources.append(f"missing_{key}_contract")
    if latest_accepted_commit is None:
        fallback_sources.append("missing_accepted_commit")

    return RuntimeSourceSnapshot(
        chapter=chapter,
        contracts=contracts,
        latest_commit=latest_commit,
        latest_accepted_commit=latest_accepted_commit,
        fallback_sources=fallback_sources,
    )
