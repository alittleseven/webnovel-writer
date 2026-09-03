"""prose_check 程序化文笔检测器（webnovel-copilot-300 · M5/T23，R2/F-02/F-18）。

把 style-adapter 的量化标准脚本化，六项检查（每项输出 阈值/实测/命中位置）：
1. 高频词库命中：references/prose-lexicon.json（A-N 十四类，polish-guide 词库），
   单类每千字命中 > 阈值记 flagged（提醒级，对应 anti_ai_force_check 需附本结果）；
2. 长句比例：>40 字（去标点）句子占比 > 阈值；
3. said tag 占比：对白段带口播动词的比例（>阈值 = 说明腔过重）；
4. 连续同句式：连续 ≥3 句以同词开头；
5. 纯解释段：无对白且超长的段落（信息过密/说明腔）；
6. 段落长度方差：变异系数过低 = 句式规整（AI 结构性特征，F-18）。

红线：只检测、不改写；词频仅提醒，是否 fail 由润色契约判断。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PROSE_CHECK_SCHEMA_VERSION = "prose-check/1"
_LEXICON_PATH = Path(__file__).resolve().parent.parent.parent / "references" / "prose-lexicon.json"

LONG_SENTENCE_CHARS = 40
LONG_SENTENCE_RATIO = 0.15
LEXICON_PER_KILO = 1.0  # 单类每千字命中阈值（提醒级）
SAID_TAG_HIGH = 0.6
REPEAT_SENTENCE_START = 3
EXPOSITION_PARA_CHARS = 300
PARA_CV_FLOOR = 0.35
_SENT_SPLIT_RE = re.compile(r"[。！？!?]+")
_DIALOGUE_RE = re.compile(r"「([^」]*)」|“([^”]*)”|\"([^\"\n]*)\"")
_SAID_VERBS = ("说", "道", "问", "答", "喊", "叫", "骂", "念", "嘀咕", "吩咐", "回答", "嚷")
_PUNCT_RE = re.compile(r"[，。！？!?：:；;、「」“”\"'\s—…·\n\r]")


def default_lexicon() -> dict[str, list[str]]:
    if not _LEXICON_PATH.is_file():
        return {}
    data = json.loads(_LEXICON_PATH.read_text(encoding="utf-8"))
    return data.get("categories", {})


def _strip_front_matter(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2]
    return text


def _paragraphs(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def check_lexicon(text: str, total_chars: int, lexicon: dict[str, list[str]]) -> dict[str, Any]:
    kilo = max(total_chars, 1) / 1000
    categories: list[dict[str, Any]] = []
    for category, words in lexicon.items():
        hits: list[dict[str, Any]] = []
        for word in words:
            for match in re.finditer(re.escape(word), text):
                paragraph_no = text.count("\n", 0, match.start()) + 1
                hits.append({"词": word, "位置": f"段{paragraph_no}", "上下文": text[max(0, match.start() - 6): match.end() + 6]})
        per_kilo = len(hits) / kilo
        if hits:
            categories.append(
                {
                    "类别": category,
                    "阈值": f"≤{LEXICON_PER_KILO}/千字",
                    "实测": f"{per_kilo:.1f}/千字",
                    "flagged": per_kilo > LEXICON_PER_KILO,
                    "命中": hits[:8],
                    "命中总数": len(hits),
                }
            )
    flagged = [c for c in categories if c["flagged"]]
    return {"name": "lexicon_hits", "阈值": f"单类≤{LEXICON_PER_KILO}/千字", "实测": f"{len(flagged)}/{len(categories)} 类超限", "flagged": bool(flagged), "categories": categories}


def check_long_sentences(text: str) -> dict[str, Any]:
    sentences = [s for s in (p.strip() for p in _SENT_SPLIT_RE.split(text)) if s]
    if not sentences:
        return {"name": "long_sentences", "阈值": f"<{LONG_SENTENCE_RATIO:.0%}", "实测": "0%", "flagged": False, "命中": []}
    lengths = [(s, len(_PUNCT_RE.sub("", s))) for s in sentences]
    longs = [(s, length) for s, length in lengths if length > LONG_SENTENCE_CHARS]
    ratio = len(longs) / len(sentences)
    return {
        "name": "long_sentences",
        "阈值": f"<{LONG_SENTENCE_RATIO:.0%}",
        "实测": f"{ratio:.0%}",
        "flagged": ratio > LONG_SENTENCE_RATIO,
        "命中": [{"句": s[:30], "长度": length} for s, length in longs[:8]],
    }


def check_said_tags(text: str) -> dict[str, Any]:
    dialogues = list(_DIALOGUE_RE.finditer(text))
    if not dialogues:
        return {"name": "said_tag_ratio", "阈值": f"≤{SAID_TAG_HIGH:.0%}", "实测": "无对白", "flagged": False, "命中": []}
    tagged = 0
    for match in dialogues:
        before = text[max(0, match.start() - 12): match.start()]
        after = text[match.end(): match.end() + 6]
        if any(verb in before or verb in after for verb in _SAID_VERBS):
            tagged += 1
    ratio = tagged / len(dialogues)
    return {"name": "said_tag_ratio", "阈值": f"≤{SAID_TAG_HIGH:.0%}", "实测": f"{ratio:.0%}", "flagged": ratio > SAID_TAG_HIGH, "命中": []}


def check_repeated_sentence_starts(text: str) -> dict[str, Any]:
    """连续同主语句（首字相同的句子 ≥3 连）——主谓宾同构的反模板特征。"""
    sentences = [s.strip() for s in (p.strip() for p in _SENT_SPLIT_RE.split(text)) if len(s.strip()) >= 4]
    runs: list[dict[str, Any]] = []
    run_head = ""
    run_count = 0
    for sentence in sentences:
        stripped = sentence.lstrip("「“\"'—…·")
        if len(stripped) < 4:
            continue
        head = stripped[:1]
        if head == run_head:
            run_count += 1
        else:
            if run_count >= REPEAT_SENTENCE_START:
                runs.append({"开头": run_head, "连续句数": run_count})
            run_head, run_count = head, 1
    if run_count >= REPEAT_SENTENCE_START:
        runs.append({"开头": run_head, "连续句数": run_count})
    return {
        "name": "repeated_sentence_starts",
        "阈值": f"连续同主语开头 <{REPEAT_SENTENCE_START} 句",
        "实测": f"{len(runs)} 处",
        "flagged": bool(runs),
        "命中": runs[:8],
    }


def check_exposition_paragraphs(text: str) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    for index, paragraph in enumerate(_paragraphs(text), start=1):
        if len(paragraph) > EXPOSITION_PARA_CHARS and not _DIALOGUE_RE.search(paragraph):
            hits.append({"段": index, "长度": len(paragraph), "开头": paragraph[:24]})
    return {
        "name": "exposition_paragraphs",
        "阈值": f"无对白段落 ≤{EXPOSITION_PARA_CHARS} 字",
        "实测": f"{len(hits)} 段",
        "flagged": bool(hits),
        "命中": hits[:8],
    }


def check_paragraph_variance(text: str) -> dict[str, Any]:
    lengths = [len(p) for p in _paragraphs(text)]
    if len(lengths) < 4:
        return {"name": "paragraph_variance", "阈值": f"变异系数 ≥{PARA_CV_FLOOR}", "实测": "段数不足", "flagged": False, "命中": []}
    mean = sum(lengths) / len(lengths)
    variance = sum((x - mean) ** 2 for x in lengths) / len(lengths)
    cv = (variance ** 0.5) / mean if mean else 0.0
    return {
        "name": "paragraph_variance",
        "阈值": f"变异系数 ≥{PARA_CV_FLOOR}",
        "实测": f"{cv:.2f}",
        "flagged": cv < PARA_CV_FLOOR,
        "命中": [],
    }


def check_prose(text: str, *, lexicon: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """六项文笔检测（只读）。返回结构化报告：每项 阈值/实测/flagged/命中位置。"""
    body = _strip_front_matter(text or "")
    lex = lexicon if lexicon is not None else default_lexicon()
    total_chars = max(len(_PUNCT_RE.sub("", body)), 1)
    checks = [
        check_lexicon(body, total_chars, lex),
        check_long_sentences(body),
        check_said_tags(body),
        check_repeated_sentence_starts(body),
        check_exposition_paragraphs(body),
        check_paragraph_variance(body),
    ]
    flagged = [c["name"] for c in checks if c["flagged"]]
    return {
        "schema_version": PROSE_CHECK_SCHEMA_VERSION,
        "ok": not flagged,
        "total_chars": total_chars,
        "flagged": flagged,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python -X utf8 prose_check.py --file <正文md> [--format json|text]

    一般经 `webnovel.py prose-check --file F` 调用（Step 4 anti_ai_force_check 必附本结果）。
    """
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="程序化文笔检测（T23/R2）")
    parser.add_argument("--file", required=True, help="正文文件（md/txt，front matter 自动剥离）")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    path = Path(args.file)
    if not path.is_file():
        print(f"ERROR file_missing: {path}")
        return 1
    report = check_prose(path.read_text(encoding="utf-8"))

    if args.format == "json":
        print(_json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    status = "PASS" if report["ok"] else "FLAG"
    print(f"{status} prose_check（{report['total_chars']} 字）flagged={report['flagged'] or '无'}")
    for check in report["checks"]:
        mark = "✗" if check["flagged"] else "✓"
        print(f"  {mark} {check['name']}: 实测 {check['实测']}（阈值 {check['阈值']}）")
        for hit in check.get("命中") or []:
            printable = hit if isinstance(hit, str) else " ".join(f"{k}={v}" for k, v in hit.items())
            print(f"      - {printable}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
