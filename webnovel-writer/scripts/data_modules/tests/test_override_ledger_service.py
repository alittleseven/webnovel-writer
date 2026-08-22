#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager
from data_modules.override_ledger_service import (
    AmendProposalTrigger,
    ensure_override_ledger_columns,
    normalize_override_record,
    persist_amend_proposals,
)


def test_normalize_override_record_sets_record_type():
    row = normalize_override_record(
        record_type="contract_override",
        field="core_tone",
        base_value="先压后爆",
        override_value="当场爆发",
        source_level="chapter",
    )
    assert row["record_type"] == "contract_override"
    assert row["field"] == "core_tone"


def test_normalize_override_record_supports_amend_proposal():
    row = normalize_override_record(
        record_type="amend_proposal",
        field="world_rule",
        base_value="金手指每日一次",
        override_value="金手指失控突破",
        source_level="master",
    )
    assert row["record_type"] == "amend_proposal"


def test_world_rule_broken_generates_amend_proposal():
    trigger = AmendProposalTrigger()
    proposals = trigger.check(
        chapter=3,
        events=[
            {
                "event_id": "evt-001",
                "event_type": "world_rule_broken",
                "subject": "金手指",
                "payload": {
                    "field": "world_rule",
                    "base_value": "每日一次",
                    "proposed_value": "短时失控突破",
                },
            }
        ],
    )
    assert len(proposals) == 1
    assert proposals[0]["target_level"] == "master"
    assert proposals[0]["field"] == "world_rule"


def test_persist_amend_proposals_writes_pending_rows(tmp_path):
    manager = IndexManager(DataModulesConfig.from_project_root(tmp_path))
    proposals = [
        {
            "proposal_id": "amend-3-evt-001",
            "chapter": 3,
            "target_level": "master",
            "field": "world_rule",
            "base_value": "每日一次",
            "proposed_value": "短时失控突破",
            "reason_tag": "world_rule_broken",
        }
    ]

    with manager._get_conn() as conn:
        ensure_override_ledger_columns(conn)
        inserted = persist_amend_proposals(conn, 3, proposals)
        conn.commit()

    with manager._get_conn() as conn:
        row = conn.execute(
            """
            SELECT record_type, field, override_value, source_level, status
            FROM override_contracts
            """
        ).fetchone()

    assert inserted == 1
    assert row["record_type"] == "amend_proposal"
    assert row["field"] == "world_rule"
    assert row["override_value"] == "短时失控突破"
    assert row["source_level"] == "master"
    assert row["status"] == "pending"


def test_power_breakthrough_generates_amend_proposal():
    trigger = AmendProposalTrigger()
    proposals = trigger.check(
        chapter=5,
        events=[
            {
                "event_id": "evt-002",
                "event_type": "power_breakthrough",
                "subject": "xiaoyan",
                "payload": {"from": "斗者", "to": "斗师"},
            }
        ],
    )
    assert len(proposals) == 1
    assert proposals[0]["target_level"] == "master"
    assert proposals[0]["reason_tag"] == "power_breakthrough"
    assert proposals[0]["base_value"] == "斗者"
    assert proposals[0]["proposed_value"] == "斗师"


def test_world_rule_revealed_generates_proposal_from_rule_content():
    trigger = AmendProposalTrigger()
    proposals = trigger.check(
        chapter=5,
        events=[
            {
                "event_id": "evt-003",
                "event_type": "world_rule_revealed",
                "subject": "luming",
                "payload": {"rule_content": "金手指每日限用一次"},
            }
        ],
    )
    assert len(proposals) == 1
    assert proposals[0]["reason_tag"] == "world_rule_revealed"
    assert proposals[0]["proposed_value"] == "金手指每日限用一次"


def test_character_state_changed_generates_proposal():
    trigger = AmendProposalTrigger()
    proposals = trigger.check(
        chapter=6,
        events=[
            {
                "event_id": "evt-004",
                "event_type": "character_state_changed",
                "subject": "xiaoyan",
                "payload": {"field": "mood", "old": "躁动", "new": "冷静"},
            }
        ],
    )
    assert len(proposals) == 1
    assert proposals[0]["field"] == "mood"
    assert proposals[0]["base_value"] == "躁动"
    assert proposals[0]["proposed_value"] == "冷静"


def test_event_without_proposed_value_does_not_generate_empty_proposal():
    trigger = AmendProposalTrigger()
    proposals = trigger.check(
        chapter=7,
        events=[
            {
                "event_id": "evt-005",
                "event_type": "power_breakthrough",
                "subject": "xiaoyan",
                "payload": {},  # 无 from/to，不应产出空提案
            }
        ],
    )
    assert proposals == []


def test_open_loop_created_does_not_generate_proposal():
    trigger = AmendProposalTrigger()
    proposals = trigger.check(
        chapter=7,
        events=[
            {
                "event_id": "evt-006",
                "event_type": "open_loop_created",
                "subject": "three_year_promise",
                "payload": {"content": "三年之约提及"},
            }
        ],
    )
    assert proposals == []
