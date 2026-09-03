#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T23（M5）prose_check 程序化文笔检测测试。

对应方案：03 R2（F-02/F-07/F-18）、08 T23。
验收契约：含已知 AI 套话的测试文本被报出具体位置；六项检查各有阈值/实测/命中；
合规文本不被误报；Step 4 anti_ai_force_check 需附本结果（CLI 出口可用）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


AI_FLAVORED = (
    "他缓缓开口，淡淡说道：\"总之，这件事就这么定了。\"\n"
    "首先，我们要明白命运的安排。其次，我们要理解成长的意义。最后，我们要接受蜕变的过程。\n"
    "她心中暗道，这一切都要从三年前说起。空气仿佛凝固，夜色如墨，四周一片寂静。\n"
    "他心中一紧，眸中闪过一丝惊讶，嘴角微微上扬，轻轻摇头，缓缓点头，心中五味杂陈。\n"
)

CLEAN = (
    "老周把扳手扔进铁盆，叮当一声。\n"
    "\"你到底修不修？\"\n"
    "\"修。\"苏小白蹲下去，手指在管壁上摸了一圈，\"但不是今天。\"\n"
    "老周骂了句什么，转身去拉电闸。\n"
)


class TestLexicon:
    def test_ai_flavored_text_hits_with_locations(self):
        from data_modules.prose_check import check_prose

        report = check_prose(AI_FLAVORED)

        lex = next(c for c in report["checks"] if c["name"] == "lexicon_hits")
        assert lex["flagged"] is True
        words = {hit["词"] for cat in lex["categories"] for hit in cat["命中"]}
        assert "总之" in words and "心中暗道" in words, "已知 AI 套话被报出"
        assert any("段1" in hit["位置"] for cat in lex["categories"] for hit in cat["命中"]), "报出具体位置"

    def test_clean_text_no_lexicon_flag(self):
        from data_modules.prose_check import check_prose

        report = check_prose(CLEAN)

        lex = next(c for c in report["checks"] if c["name"] == "lexicon_hits")
        assert lex["flagged"] is False


class TestStructureChecks:
    def test_long_sentence_ratio_flagged(self):
        from data_modules.prose_check import check_long_sentences

        body = "这是一段没有任何标点分隔并且不断延伸的长句子" * 8 + "。"
        report = check_long_sentences(body)

        assert report["flagged"] is True
        assert report["命中"], "报出长句样本"

    def test_repeated_sentence_starts_flagged(self):
        from data_modules.prose_check import check_repeated_sentence_starts

        body = "他走了。他看见门。他推开门。他坐下了。"
        report = check_repeated_sentence_starts(body)

        assert report["flagged"] is True
        assert report["命中"][0]["开头"] == "他"

    def test_exposition_paragraph_flagged(self):
        from data_modules.prose_check import check_exposition_paragraphs

        body = "说明" * 200
        report = check_exposition_paragraphs(body)

        assert report["flagged"] is True
        assert report["命中"][0]["段"] == 1

    def test_paragraph_variance_flagged_for_uniform_text(self):
        from data_modules.prose_check import check_paragraph_variance

        body = "\n".join("字" * 100 for _ in range(8))
        report = check_paragraph_variance(body)

        assert report["flagged"] is True, "段落长度整齐 = 句式规整（F-18）"

    def test_said_tag_ratio_reported(self):
        from data_modules.prose_check import check_said_tags

        body = "他说：\"好。\"她说道：\"行。\"他喊道：\"快跑。\""
        report = check_said_tags(body)

        assert report["实测"].endswith("%")


class TestOverall:
    def test_clean_text_passes(self):
        from data_modules.prose_check import check_prose

        report = check_prose(CLEAN)

        assert report["ok"] is True
        assert report["flagged"] == []

    def test_ai_flavored_text_flagged(self):
        from data_modules.prose_check import check_prose

        report = check_prose(AI_FLAVORED)

        assert report["ok"] is False
        assert len(report["flagged"]) >= 3

    def test_front_matter_stripped(self):
        from data_modules.prose_check import check_prose

        text = "---\n章号: 1\n---\n" + CLEAN
        report = check_prose(text)

        assert report["ok"] is True, "front matter 不参与检测"

    def test_cli_json_and_exit_code(self, tmp_path: Path, capsys):
        from data_modules.prose_check import main

        bad = tmp_path / "bad.md"
        bad.write_text(AI_FLAVORED, encoding="utf-8")
        assert main(["--file", str(bad), "--format", "json"]) == 1, "flagged 文本非零退出（阻断润色通过）"
        import json

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is False

        good = tmp_path / "good.md"
        good.write_text(CLEAN, encoding="utf-8")
        assert main(["--file", str(good)]) == 0
