#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
from typing import Dict, List

from .amend_proposal_schema import AmendProposal


def normalize_override_record(
    *,
    record_type: str,
    field: str,
    base_value: str,
    override_value: str,
    source_level: str,
) -> Dict[str, str]:
    return {
        "record_type": str(record_type or "").strip(),
        "field": str(field or "").strip(),
        "base_value": str(base_value or "").strip(),
        "override_value": str(override_value or "").strip(),
        "source_level": str(source_level or "").strip(),
    }


def ensure_override_ledger_columns(conn: sqlite3.Connection) -> None:
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(override_contracts)").fetchall()
    }
    wanted = {
        "record_type": "TEXT DEFAULT 'soft_deviation'",
        "field": "TEXT DEFAULT ''",
        "base_value": "TEXT DEFAULT ''",
        "override_value": "TEXT DEFAULT ''",
        "source_level": "TEXT DEFAULT ''",
        "reason_tag": "TEXT DEFAULT ''",
    }
    for name, ddl in wanted.items():
        if name not in existing:
            # SECURITY: name 和 ddl 均来自上方硬编码字典，非用户输入，无 SQL 注入风险
            conn.execute(f"ALTER TABLE override_contracts ADD COLUMN {name} {ddl}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_override_contracts_record_type ON override_contracts(record_type)"
    )


class AmendProposalTrigger:
    """事件 → 合同修订提案触发规则。

    审计（P0-3b）发现原 RULES 中 10 个事件类型 9 个映射 None，仅 world_rule_broken
    产生提案，修订提案机制名存实亡。本实现为会改变世界规则 / 力量体系 / 角色状态的
    高价值事件补全提案规则，并对 payload 字段缺失做降级（有值才产出，避免空提案）。

    每个规则形如：{"target_level", "reason_tag", "field", "base", "proposed"}，
    其中 field/base/proposed 是 payload 中字段名的候选列表（按优先级取第一个非空）。
    """

    # payload 字段候选：优先取明确旧值/新值，其次取语义内容。
    RULES = {
        "world_rule_broken": {
            "target_level": "master",
            "reason_tag": "world_rule_broken",
            "field": ["field", "rule_name", "rule_id"],
            "base": ["base_value", "old", "old_rule"],
            "proposed": ["proposed_value", "new", "new_rule", "rule_content"],
        },
        "world_rule_revealed": {
            "target_level": "master",
            "reason_tag": "world_rule_revealed",
            "field": ["field", "rule_category", "rule_name"],
            "base": ["base_value", "old"],
            "proposed": ["rule_content", "proposed_value", "new"],
        },
        "power_breakthrough": {
            "target_level": "master",
            "reason_tag": "power_breakthrough",
            "field": ["field", "power_system", "realm_field"],
            "base": ["base_value", "from", "old"],
            "proposed": ["proposed_value", "to", "new"],
        },
        "character_state_changed": {
            "target_level": "master",
            "reason_tag": "character_state_changed",
            "field": ["field", "state_field"],
            "base": ["base_value", "old"],
            "proposed": ["proposed_value", "new"],
        },
        # 以下事件不改变合同事实，不产生提案（保留为显式 None 表意清晰）。
        "relationship_changed": None,
        "artifact_obtained": None,
        "open_loop_created": None,
        "open_loop_closed": None,
        "promise_created": None,
        "promise_paid_off": None,
    }

    @staticmethod
    def _pick(payload: dict, keys: List[str]) -> str:
        for key in keys:
            value = payload.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    def check(self, chapter: int, events: List[dict]) -> List[Dict[str, str | int]]:
        proposals: List[Dict[str, str | int]] = []
        for event in events or []:
            if not isinstance(event, dict):
                continue
            rule = self.RULES.get(str(event.get("event_type") or "").strip())
            if not rule:
                continue
            payload = dict(event.get("payload") or {})
            field = self._pick(payload, rule.get("field") or [])
            base_value = self._pick(payload, rule.get("base") or [])
            proposed_value = self._pick(payload, rule.get("proposed") or [])

            # 提案三要素（field/base/proposed）至少要有 proposed_value，且 field 可推断，
            # 否则产出的是无意义的空提案，反而污染覆写账本。
            if not proposed_value:
                continue

            proposal = AmendProposal(
                proposal_id=f"amend-{chapter}-{event.get('event_id')}",
                chapter=chapter,
                target_level=rule["target_level"],
                field=field or str(rule.get("reason_tag") or ""),
                base_value=base_value,
                proposed_value=proposed_value,
                reason_tag=rule["reason_tag"],
            )
            proposals.append(proposal.model_dump())
        return proposals


def persist_amend_proposals(
    conn: sqlite3.Connection, chapter: int, proposals: List[dict]
) -> int:
    inserted = 0
    for proposal in proposals or []:
        row = normalize_override_record(
            record_type="amend_proposal",
            field=str(proposal.get("field") or ""),
            base_value=str(proposal.get("base_value") or ""),
            override_value=str(proposal.get("proposed_value") or ""),
            source_level=str(proposal.get("target_level") or ""),
        )
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO override_contracts (
                chapter,
                constraint_type,
                constraint_id,
                rationale_type,
                rationale_text,
                payback_plan,
                due_chapter,
                status,
                record_type,
                field,
                base_value,
                override_value,
                source_level,
                reason_tag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chapter,
                "AMEND_PROPOSAL",
                str(proposal.get("proposal_id") or ""),
                "story_amend_proposal",
                f"事件触发合同修订提案: {proposal.get('proposal_id')}",
                "",
                chapter,
                "pending",
                row["record_type"],
                row["field"],
                row["base_value"],
                row["override_value"],
                row["source_level"],
                str(proposal.get("reason_tag") or ""),
            ),
        )
        inserted += max(int(cursor.rowcount), 0)
    return inserted
