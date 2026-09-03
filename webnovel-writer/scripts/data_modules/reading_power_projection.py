"""追读力投影 writer（webnovel-copilot-300 · M5/T25，R4/F-05）。

accepted 提交在投影链自动落 `chapter_reading_power` 表——数据源为 data-agent
extraction_result 的钩子字段（顶层 `hook_type`/`hook_strength`，或摘要 front
matter 中的同名键）；无钩子字段时 skipped（不阻断提交）。
此投影闭合 F-05「追读力指标无生产者」：写前指导的钩子差异化/爽点去重从此有据。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_HOOK_TYPE_RE = re.compile(r"^hook_type:\s*[\"']?([^\n\"']+)", re.MULTILINE)
_HOOK_STRENGTH_RE = re.compile(r"^hook_strength:\s*[\"']?([^\n\"']+)", re.MULTILINE)


def extract_hook_fields(extraction_result: dict[str, Any]) -> tuple[str, str]:
    """从 extraction_result 取钩子字段：顶层键优先，其次摘要 front matter。"""
    if not isinstance(extraction_result, dict):
        return "", ""
    hook_type = str(extraction_result.get("hook_type") or "").strip()
    hook_strength = str(extraction_result.get("hook_strength") or "").strip()
    if hook_type and hook_strength:
        return hook_type, hook_strength
    summary = str(extraction_result.get("summary_text") or "")
    if summary.startswith("---"):
        if not hook_type:
            match = _HOOK_TYPE_RE.search(summary)
            if match:
                hook_type = match.group(1).strip()
        if not hook_strength:
            match = _HOOK_STRENGTH_RE.search(summary)
            if match:
                hook_strength = match.group(1).strip()
    return hook_type, hook_strength


class ReadingPowerProjectionWriter:
    name = "reading_power"

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def apply(self, commit_payload: dict) -> dict:
        status = str((commit_payload.get("meta") or {}).get("status") or "")
        if status != "accepted":
            return {"applied": False, "writer": self.name, "reason": "commit_rejected"}
        extraction = commit_payload.get("extraction_result") or {}
        hook_type, hook_strength = extract_hook_fields(extraction if isinstance(extraction, dict) else {})
        if not hook_type:
            return {"applied": False, "writer": self.name, "reason": "not_required"}
        try:
            from .config import DataModulesConfig
            from .index_manager import ChapterReadingPowerMeta, IndexManager

            meta = ChapterReadingPowerMeta(
                chapter=int((commit_payload.get("meta") or {}).get("chapter") or 0),
                hook_type=hook_type,
                hook_strength=hook_strength or "medium",
            )
            IndexManager(DataModulesConfig.from_project_root(self.project_root)).save_chapter_reading_power(meta)
        except Exception as exc:  # noqa: BLE001 - 投影失败走 failed 状态，不中断链
            return {"applied": False, "writer": self.name, "reason": f"error:{exc}"}
        return {"applied": True, "writer": self.name, "chapter": meta.chapter, "hook_type": hook_type}
