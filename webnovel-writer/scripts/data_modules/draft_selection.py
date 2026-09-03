"""多稿择优（webnovel-copilot-300 · M5/T24，R3/F-03，D0-4 默认 2 稿）。

起草-自评-重写循环的数据面：
- 固定质量 rubric 六维（钩子强度/情绪弧/场景必要性/信息密度/对话声线区分/
  结尾未完感，每项 1-5 分 + 一句话理由，见 references/draft-rubric.md）；
- 稿间互不可见，各自独立自评后落库 `draft_evaluations` 表（index.db）；
- `choose_draft` 择优：取平均分最高稿进 Step 3；全部低于阈值（均分 <3.5）时
  按 rubric 最弱项给出一次定向重写提示；
- `link_review_score` 把最终审查分回填到选中稿——rubric 与审查分的长期校准数据。

红线：择优只依据 rubric 分（结构化）；session 负责实际起草 N 稿（本模块不生成文本）。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import connect

DRAFT_SCHEMA_VERSION = "draft-selection/1"
RUBRIC_DIMENSIONS: tuple[str, ...] = ("钩子强度", "情绪弧", "场景必要性", "信息密度", "对话声线区分", "结尾未完感")
BEST_SCORE_FLOOR = 3.5
_REWRITE_ONCE_FLAG = "_rewrite_done"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _conn(project_root: Path) -> sqlite3.Connection:
    conn = connect(Path(project_root) / ".webnovel" / "index.db")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS draft_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter INTEGER NOT NULL,
            draft_no INTEGER NOT NULL,
            scores_json TEXT NOT NULL,
            rationale TEXT NOT NULL DEFAULT '',
            total REAL NOT NULL,
            chosen INTEGER NOT NULL DEFAULT 0,
            review_score REAL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def record_draft(
    project_root: str | Path,
    *,
    chapter: int,
    draft_no: int,
    scores: dict[str, float],
    rationale: str = "",
) -> dict[str, Any]:
    """登记一稿的 rubric 自评（六维 1-5 分；新稿登记自动取消既有选中标记）。"""
    missing = [dim for dim in RUBRIC_DIMENSIONS if dim not in scores]
    if missing:
        return {"ok": False, "error": "missing_dimensions", "missing": missing}
    values: dict[str, float] = {}
    for dim in RUBRIC_DIMENSIONS:
        try:
            value = float(scores[dim])
        except (TypeError, ValueError):
            return {"ok": False, "error": "invalid_score", "dimension": dim}
        if not 1 <= value <= 5:
            return {"ok": False, "error": "score_out_of_range", "dimension": dim, "value": value}
        values[dim] = value
    total = round(sum(values.values()) / len(values), 2)

    conn = _conn(Path(project_root))
    try:
        conn.execute("UPDATE draft_evaluations SET chosen = 0 WHERE chapter = ?", (int(chapter),))
        conn.execute(
            "INSERT INTO draft_evaluations (chapter, draft_no, scores_json, rationale, total, chosen, created_at)"
            " VALUES (?, ?, ?, ?, ?, 0, ?)",
            (int(chapter), int(draft_no), json.dumps(values, ensure_ascii=False), str(rationale), total, _utc_now_iso()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "schema_version": DRAFT_SCHEMA_VERSION, "chapter": int(chapter), "draft_no": int(draft_no), "total": total}


def choose_draft(project_root: str | Path, *, chapter: int) -> dict[str, Any]:
    """择优：最高均分稿标 chosen；均分 < 3.5（未重写过）给最弱项定向重写提示。"""
    conn = _conn(Path(project_root))
    try:
        rows = conn.execute(
            "SELECT id, draft_no, scores_json, total, chosen FROM draft_evaluations WHERE chapter = ? ORDER BY total DESC, draft_no ASC",
            (int(chapter),),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return {"ok": False, "error": "no_drafts", "chapter": int(chapter)}

    best = dict(rows[0])
    conn = _conn(Path(project_root))
    try:
        conn.execute("UPDATE draft_evaluations SET chosen = CASE WHEN id = ? THEN 1 ELSE 0 END WHERE chapter = ?", (best["id"], int(chapter)))
        conn.commit()
        flags = conn.execute(
            "SELECT COUNT(*) AS n FROM draft_evaluations WHERE chapter = ? AND rationale LIKE ?",
            (int(chapter), f"%{_REWRITE_ONCE_FLAG}%"),
        ).fetchone()
        already = int(flags["n"] or 0) > 0
    finally:
        conn.close()

    report: dict[str, Any] = {
        "ok": True,
        "schema_version": DRAFT_SCHEMA_VERSION,
        "chapter": int(chapter),
        "drafts": len(rows),
        "chosen_draft_no": int(best["draft_no"]),
        "chosen_total": float(best["total"]),
        "scores": json.loads(best["scores_json"]),
    }
    if float(best["total"]) < BEST_SCORE_FLOOR and not already:
        scores = json.loads(best["scores_json"])
        weakest = min(RUBRIC_DIMENSIONS, key=lambda dim: scores.get(dim, 5))
        report["rewrite_hint"] = {
            "dimension": weakest,
            "note": f"全部稿件均分低于 {BEST_SCORE_FLOOR}：按 rubric 最弱项「{weakest}」定向重写一次（最多 1 次）",
        }
    return report


def link_review_score(project_root: str | Path, *, chapter: int, review_score: float) -> dict[str, Any]:
    """最终审查分回填到选中稿（rubric ↔ 审查分对照校准数据）。"""
    conn = _conn(Path(project_root))
    try:
        cursor = conn.execute(
            "UPDATE draft_evaluations SET review_score = ? WHERE chapter = ? AND chosen = 1",
            (float(review_score), int(chapter)),
        )
        conn.commit()
        updated = cursor.rowcount
    finally:
        conn.close()
    if not updated:
        return {"ok": False, "error": "no_chosen_draft", "chapter": int(chapter)}
    return {"ok": True, "chapter": int(chapter), "review_score": float(review_score)}


def report(project_root: str | Path, *, chapter: int) -> dict[str, Any]:
    conn = _conn(Path(project_root))
    try:
        rows = conn.execute(
            "SELECT draft_no, scores_json, rationale, total, chosen, review_score, created_at"
            " FROM draft_evaluations WHERE chapter = ? ORDER BY draft_no ASC",
            (int(chapter),),
        ).fetchall()
    finally:
        conn.close()
    drafts = [
        {
            "draft_no": int(row["draft_no"]),
            "scores": json.loads(row["scores_json"]),
            "rationale": row["rationale"],
            "total": float(row["total"]),
            "chosen": bool(row["chosen"]),
            "review_score": row["review_score"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return {"ok": True, "schema_version": DRAFT_SCHEMA_VERSION, "chapter": int(chapter), "drafts": drafts}


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python -X utf8 draft_selection.py {record|choose|link|report} [options]

    一般经 `webnovel.py drafts <action>` 调用（write SKILL Step 2 落库出口）。
    """
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="多稿择优数据面（T24/R3）")
    parser.add_argument("action", choices=["record", "choose", "link", "report"])
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--draft", type=int, default=None, help="record：稿号")
    parser.add_argument("--scores", default="", help="record：逗号分隔 维:分（六维）")
    parser.add_argument("--rationale", default="", help="record：一句话理由（重写标记写于此）")
    parser.add_argument("--score", type=float, default=None, help="link：最终审查分")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    if args.action == "record":
        if args.draft is None:
            parser.error("record 需要 --draft")
        scores = {}
        for part in args.scores.split(","):
            if part.strip() and ":" in part:
                key, _, value = part.partition(":")
                scores[key.strip()] = value.strip()
        report_data = record_draft(root, chapter=args.chapter, draft_no=args.draft, scores=scores, rationale=args.rationale)
    elif args.action == "choose":
        report_data = choose_draft(root, chapter=args.chapter)
    elif args.action == "link":
        if args.score is None:
            parser.error("link 需要 --score")
        report_data = link_review_score(root, chapter=args.chapter, review_score=args.score)
    else:
        report_data = report(root, chapter=args.chapter)

    if args.format == "json":
        print(_json.dumps(report_data, ensure_ascii=False, indent=2))
        return 0 if report_data.get("ok", True) else 1

    if args.action == "record":
        print("OK 已登记" if report_data.get("ok") else f"ERROR {report_data.get('error')} {report_data.get('missing') or report_data.get('dimension') or ''}")
    elif args.action == "choose":
        if not report_data.get("ok"):
            print(f"ERROR {report_data.get('error')}")
        else:
            print(f"OK 选中稿 {report_data['chosen_draft_no']}（均分 {report_data['chosen_total']}，共 {report_data['drafts']} 稿）")
            if report_data.get("rewrite_hint"):
                print(f"  REWRITE {report_data['rewrite_hint']['note']}")
    elif args.action == "link":
        print("OK 审查分已回填" if report_data.get("ok") else f"ERROR {report_data.get('error')}")
    else:
        for item in report_data["drafts"]:
            chosen = " ←选中" if item["chosen"] else ""
            review = f"｜审查 {item['review_score']}" if item["review_score"] is not None else ""
            print(f"稿{item['draft_no']}  均分 {item['total']}{chosen}{review}")
        if not report_data["drafts"]:
            print("(无登记)")
    return 0 if report_data.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
