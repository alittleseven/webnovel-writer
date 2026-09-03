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

    # 素材使用轨迹落账（webnovel-copilot-300 M2/T12）：静默，绝不阻断写章事务
    try:
        from data_modules.material_usage import settle_materials_for_chapter

        if settle_materials_for_chapter(Path(args.project_root), args.chapter):
            print("materials: 素材引用轨迹已落账")
    except Exception as exc:  # noqa: BLE001 - 轨迹失败不影响提交
        print(f"materials: 轨迹落账跳过（{exc}）")

    # 文风域落账（webnovel-copilot-300 M3/T17 + F-11）：高分采样 + 指纹增量，静默不阻断
    try:
        from data_modules.style_domain import settle_style_domain

        style_report = settle_style_domain(
            Path(args.project_root),
            chapter=args.chapter,
            review_file=args.review_result,
            extraction_file=args.extraction_result,
        )
        if style_report.get("recorded"):
            print(f"style: 高分样本 +{style_report['recorded']}，指纹已更新（{style_report['fingerprint_chapters']} 章）")
    except Exception as exc:  # noqa: BLE001 - 文风落账失败不影响提交
        print(f"style: 文风落账跳过（{exc}）")

    print(summarize_commit_payload(payload))


if __name__ == "__main__":
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
