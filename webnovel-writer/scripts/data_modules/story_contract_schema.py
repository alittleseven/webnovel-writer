#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


# P1-2：合同 schema 当前版本常量。新增字段/结构变更时递增，并在
# contract_migrations.CONTRACT_MIGRATIONS 注册迁移函数。
CONTRACT_SCHEMA_VERSION = "story-system/v1"


class ContractMeta(BaseModel):
    schema_version: str = CONTRACT_SCHEMA_VERSION
    contract_type: str
    generator_version: str = "phase2"
    source_trace: List[Dict[str, Any]] = Field(default_factory=list)


class OverrideBundle(BaseModel):
    locked: Dict[str, Any] = Field(default_factory=dict)
    append_only: Dict[str, Any] = Field(default_factory=dict)
    override_allowed: Dict[str, Any] = Field(default_factory=dict)


class MasterSetting(BaseModel):
    meta: ContractMeta
    route: Dict[str, Any] = Field(default_factory=dict)
    master_constraints: Dict[str, Any] = Field(default_factory=dict)
    base_context: List[Dict[str, Any]] = Field(default_factory=list)
    source_trace: List[Dict[str, Any]] = Field(default_factory=list)
    override_policy: Dict[str, List[str]] = Field(default_factory=dict)


class ChapterBrief(BaseModel):
    meta: ContractMeta
    override_allowed: Dict[str, Any] = Field(default_factory=dict)
    chapter_directive: Dict[str, Any] = Field(default_factory=dict)
    dynamic_context: List[Dict[str, Any]] = Field(default_factory=list)
    source_trace: List[Dict[str, Any]] = Field(default_factory=list)


class VolumeBrief(BaseModel):
    meta: ContractMeta
    volume_goal: Dict[str, Any]
    selected_tropes: List[str] = Field(default_factory=list)
    selected_pacing: Dict[str, Any] = Field(default_factory=dict)
    selected_scenes: List[str] = Field(default_factory=list)
    anti_patterns: List[str] = Field(default_factory=list)
    system_constraints: List[str] = Field(default_factory=list)
    overrides: OverrideBundle = Field(default_factory=OverrideBundle)


class ReviewContract(BaseModel):
    meta: ContractMeta
    must_check: List[str] = Field(default_factory=list)
    blocking_rules: List[str] = Field(default_factory=list)
    genre_specific_risks: List[str] = Field(default_factory=list)
    anti_patterns: List[str] = Field(default_factory=list)
    system_constraints: List[str] = Field(default_factory=list)
    review_thresholds: Dict[str, Any] = Field(default_factory=dict)
    overrides: OverrideBundle = Field(default_factory=OverrideBundle)
