#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from runtime_compat import enable_windows_utf8_stdio

from data_modules.chapter_commit_service import ChapterCommitService, summarize_commit_payload


def _read_json(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(
            f"ERROR chapter-commit: artifact JSON 无法解析（常见原因：字符串含未转义引号）: {path}\n  {exc}\n  请修复该 artifact 后重跑。",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    except OSError as exc:
        print(
            f"ERROR chapter-commit: artifact 读取失败: {path}\n  {exc}",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Chapter commit CLI")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--review-result", required=True)
    parser.add_argument("--fulfillment-result", required=True)
    parser.add_argument("--disambiguation-result", required=True)
    parser.add_argument("--extraction-result", required=True)
    args = parser.parse_args()

    service = ChapterCommitService(Path(args.project_root))
    payload = service.build_commit(
        chapter=args.chapter,
        review_result=_read_json(args.review_result),
        fulfillment_result=_read_json(args.fulfillment_result),
        disambiguation_result=_read_json(args.disambiguation_result),
        extraction_result=_read_json(args.extraction_result),
    )
    service.persist_commit(payload)
    payload = service.apply_projections(payload)
    print(summarize_commit_payload(payload))


if __name__ == "__main__":
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
