"""reader_signal 构建器（webnovel-copilot-300 · M5/T25，R4/F-06）。

消费端闭环：近期追读力 + 钩子类型分布 + 审查趋势汇总 → load-context 的
`reader_signal` section（主路径 memory_contract_adapter 消费）；
`index get-reader-signals` 补 `review_trend` 字段。
`derive_differentiation_reminder`：连续两章同型钩子 → 第三章差异化提醒
（writing_guidance hook_diversification 的主路径等价实现）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

REMINDER_TEMPLATE = "连续 {count} 章同型钩子「{hook_type}」：本章钩子必须差异化（换钩型/换强度/换落点）"
_REVIEW_TREND_LIMIT = 5
_RECENT_LIMIT = 5


def derive_differentiation_reminder(recent_reading_power: list[dict[str, Any]], *, min_streak: int = 2) -> str:
    """最近章节（按章号降序）钩子类型连续同型 → 差异化提醒；否则空串。"""
    streak_type = ""
    streak_count = 0
    for row in recent_reading_power:
        hook_type = str(row.get("hook_type") or "").strip()
        if not hook_type:
            break
        if hook_type == streak_type:
            streak_count += 1
        elif streak_count < min_streak:
            streak_type = hook_type
            streak_count = 1
        else:
            break
    if streak_count >= min_streak and streak_type:
        return REMINDER_TEMPLATE.format(count=streak_count, hook_type=streak_type)
    return ""


def build_reader_signal(project_root: Path | str) -> dict[str, Any]:
    """汇总追读力信号（只读；index.db 缺失时优雅降级为空结构）。"""
    root = Path(project_root)
    if not (root / ".webnovel" / "index.db").is_file():
        return {
            "recent_reading_power": [],
            "hook_type_usage": {},
            "review_trend": [],
            "differentiation_reminder": "",
        }
    try:
        from .config import DataModulesConfig
        from .index_manager import IndexManager

        manager = IndexManager(DataModulesConfig.from_project_root(root))
        recent = manager.get_recent_reading_power(_RECENT_LIMIT)
        return {
            "recent_reading_power": recent,
            "hook_type_usage": manager.get_hook_type_stats(20),
            "review_trend": manager.get_recent_review_metrics(_REVIEW_TREND_LIMIT),
            "differentiation_reminder": derive_differentiation_reminder(recent),
        }
    except Exception:  # noqa: BLE001 - 信号缺失不阻断装配
        return {
            "recent_reading_power": [],
            "hook_type_usage": {},
            "review_trend": [],
            "differentiation_reminder": "",
        }
