#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T17（M3）style_anchor 接线测试（= 质量审阅 W6/R6/F-08）。

对应方案：03-recommendations R6（accepted 且 overall_score ≥85 的章节自动 style extract；
load-context 注入 style_anchor section：1 段高分原文 + 语气节奏参照）、08 T17。
契约：≥85 分才采样入库；装配注入 author_model（T16）与 style_anchor 两个 section；
settle 链（chapter-commit 后）静默完成采样 + 指纹增量。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


SAMPLE_SCENE = {
    "index": 1,
    "start_line": 1,
    "end_line": 10,
    "location": "码头",
    "summary": "对峙升级，主角亮出底牌",
    "characters": ["苏小白"],
    "content": (
        "纸人从袖口滑出来的时候，赵姓汉子的笑还挂在脸上。苏小白没看他，只看着地上那张纸。"
        "纸上有字，字是他的名字。他把名字踩进泥里，抬头时嗓音很平：「账，今天清。」"
        "码头上的风忽然停了。吊桥的铁链吱呀作响，看热闹的人群往后退了半步，"
        "又忍不住伸长脖子。赵姓汉子低头看自己的手，手指正在变得透明。"
        "「你到底是什么东西？」他喊。苏小白弯腰捡起那张纸，吹了吹上面的泥，"
        "折好，放回袖子里。夜班工牌在他胸口晃了一下，塑料壳上还印着便利店的logo。"
        "灾雾从江面上漫过来，把三个人围成一圈剪影。"
    ),
}


@pytest.fixture()
def cfg(tmp_path: Path):
    from data_modules.config import DataModulesConfig

    config = DataModulesConfig.from_project_root(tmp_path)
    config.ensure_dirs()
    config.state_file.write_text("{}", encoding="utf-8")
    (tmp_path / "book.yaml").write_text('spec_version: "7.0"\n卷规模: 40\n', encoding="utf-8")
    return config


class TestRecordStyleSamples:
    def test_high_score_chapter_records_samples(self, cfg):
        from data_modules.style_domain import record_style_samples

        report = record_style_samples(
            cfg.project_root, chapter=37, content=SAMPLE_SCENE["content"], review_score=92, scenes=[SAMPLE_SCENE]
        )

        assert report["ok"] is True
        assert report["recorded"] == 1

    def test_below_threshold_records_nothing(self, cfg):
        from data_modules.style_domain import record_style_samples

        report = record_style_samples(
            cfg.project_root, chapter=38, content=SAMPLE_SCENE["content"], review_score=84, scenes=[SAMPLE_SCENE]
        )

        assert report["recorded"] == 0, "R6：overall_score ≥85 才采样"

    def test_build_anchor_section(self, cfg):
        from data_modules.style_domain import build_style_anchor_section, record_style_samples

        assert build_style_anchor_section(cfg.project_root) == {}, "无高分样本时 section 为空"

        record_style_samples(
            cfg.project_root, chapter=37, content=SAMPLE_SCENE["content"], review_score=92, scenes=[SAMPLE_SCENE]
        )
        section = build_style_anchor_section(cfg.project_root)

        assert "语气节奏参照" in section["说明"]
        assert len(section["样本"]) <= 500, "R6：注入 1 段 300-500 字"
        assert section["章"] == 37
        assert "对话占比" in section["指纹摘要"] or section["指纹摘要"] == {}

    def test_anchor_includes_fingerprint_digest(self, cfg, tmp_path: Path):
        from data_modules.style_domain import build_style_anchor_section, record_style_samples, write_fingerprint_from_book

        chapter_dir = tmp_path / "定稿" / "正文"
        chapter_dir.mkdir(parents=True, exist_ok=True)
        (chapter_dir / "0001-天裂.md").write_text(
            "---\n章号: 1\n标题: 天裂\n---\n\n他倒是笑了一下。「走吧。」\n", encoding="utf-8"
        )
        write_fingerprint_from_book(tmp_path)
        record_style_samples(
            tmp_path, chapter=37, content=SAMPLE_SCENE["content"], review_score=90, scenes=[SAMPLE_SCENE]
        )

        section = build_style_anchor_section(tmp_path)

        assert section["指纹摘要"]["对话占比"] is not None
        assert "句长均值" in section["指纹摘要"]


class TestSettleHook:
    def test_settle_records_and_updates_fingerprint(self, cfg, tmp_path: Path):
        from data_modules.style_domain import fingerprint_path, settle_style_domain

        chapter_dir = tmp_path / "定稿" / "正文"
        chapter_dir.mkdir(parents=True, exist_ok=True)
        (chapter_dir / "0001-天裂.md").write_text(
            "---\n章号: 1\n标题: 天裂\n---\n\n他倒是笑了一下。「走吧。」\n", encoding="utf-8"
        )
        review_file = tmp_path / "review.json"
        review_file.write_text(json.dumps({"overall_score": 91, "issues": []}, ensure_ascii=False), encoding="utf-8")
        extraction_file = tmp_path / "extraction.json"
        extraction_file.write_text(json.dumps({"scenes": [SAMPLE_SCENE]}, ensure_ascii=False), encoding="utf-8")

        report = settle_style_domain(tmp_path, chapter=1, review_file=review_file, extraction_file=extraction_file)

        assert report["ok"] is True
        assert report["recorded"] == 1
        assert fingerprint_path(tmp_path).is_file(), "settle 后指纹增量更新（F-11）"

    def test_settle_skips_blocking_review(self, cfg, tmp_path: Path):
        from data_modules.style_domain import settle_style_domain
        from data_modules.style_sampler import StyleSampler

        review_file = tmp_path / "review.json"
        review_file.write_text(
            json.dumps({"overall_score": 95, "issues": [{"severity": "critical", "blocking": True, "category": "other", "title": "x", "detail": "y"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        extraction_file = tmp_path / "extraction.json"
        extraction_file.write_text(json.dumps({"scenes": [SAMPLE_SCENE]}), encoding="utf-8")

        report = settle_style_domain(tmp_path, chapter=1, review_file=review_file, extraction_file=extraction_file)

        assert report["recorded"] == 0, "被否决的章不进高分样本"
        assert StyleSampler(cfg).get_best_samples(limit=5) == []


class TestContextInjection:
    def test_build_context_includes_style_anchor_and_author_model(self, cfg, tmp_path: Path):
        from data_modules.author_model import apply_suggestion, learn_from_journal
        from data_modules.context_manager import ContextManager
        from data_modules.style_domain import record_style_samples

        record_style_samples(
            tmp_path, chapter=37, content=SAMPLE_SCENE["content"], review_score=90, scenes=[SAMPLE_SCENE]
        )
        (tmp_path / "作者").mkdir(exist_ok=True)
        (tmp_path / "作者" / "author_model.md").write_text("# 作者模型\n- 冲突前置\n", encoding="utf-8")
        (tmp_path / "作者" / "跨书偏好.yaml").write_text(
            "节奏:\n  冲突前置: true\n审稿习惯:\n  接受AI建议率: 0.6\n", encoding="utf-8"
        )

        payload = ContextManager(cfg).build_context(chapter=1)

        assert payload["style_anchor"]["章"] == 37
        assert "语气节奏参照" in payload["style_anchor"]["说明"]
        assert "冲突前置" in payload["author_model"]["模型要点"]
        assert "接受AI建议率" in payload["author_model"]["跨书偏好"]

    def test_sections_absent_clean_when_no_data(self, cfg):
        from data_modules.context_manager import ContextManager

        payload = ContextManager(cfg).build_context(chapter=1)

        assert not payload.get("style_anchor"), "无高分样本时 style_anchor 为空"
        assert not any((payload.get("author_model") or {}).values()), "无模型文件时 author_model 内容为空"
