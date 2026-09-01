#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v7_cache — v7 story-repo 的 `.cache/index.db` 全量重建与查询（S17/E2）。

不变量「派生物可丢弃」：`.cache/` 是唯一允许的派生缓存，删光后 `rebuild_cache`
从源文件（book.yaml / 定稿/ / 记忆）全量重建，`verify_rebuild` 以查询快照等价
作为验收。缓存不遮蔽真相：每次 rebuild 都重新读源。

查询面（E2 范围）：章节（get_chapter）、实体（find_entity）、章摘要（get_summary）。
v7 引擎的全量查询面在 S19 垂直切片中扩展。
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional


def cache_path(repo_root: Path) -> Path:
    return Path(repo_root) / ".cache" / "index.db"


# ---------- 源文件解析（缓存不遮蔽真相：每次 rebuild 重读源） ----------


def _parse_book_yaml(repo_root: Path) -> dict[str, str]:
    """book.yaml 平铺键值解析（值可带引号）。"""
    result: dict[str, str] = {}
    path = Path(repo_root) / "book.yaml"
    if not path.exists():
        return result
    for line in _read(path).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        result[key.strip()] = value.strip().strip('"')
    return result


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """解析 `--- ... ---` 平铺 front matter，返回 (字段, 正文)。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fields: dict[str, str] = {}
    for line in parts[1].splitlines():
        line = line.strip()
        if line and ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields, parts[2].lstrip("\n")


def _parse_chapter_filename(name: str) -> tuple[Optional[int], str]:
    m = re.match(r"(\d{4})-(.*)\.md", name)
    if not m:
        return None, name
    return int(m.group(1)), m.group(2)


def _iter_chapters(repo_root: Path):
    body_dir = Path(repo_root) / "定稿" / "正文"
    if not body_dir.exists():
        return
    for path in sorted(body_dir.glob("*.md")):
        num, filename_title = _parse_chapter_filename(path.name)
        if num is None:
            continue
        fields, body = _parse_front_matter(_read(path))
        yield {
            "num": num,
            "title": fields.get("标题") or filename_title,
            "volume": int(fields["卷"]) if fields.get("卷", "").isdigit() else 1,
            "words": int(fields["字数"]) if fields.get("字数", "").isdigit() else len(re.sub(r"\s", "", body)),
            "file": str(path.relative_to(repo_root)),
            "body": body,
        }


def _iter_roster(repo_root: Path):
    """名册双落点兼容（审阅报告 P1 修复）。

    - `名册.md` 单表：S16 迁移器产物（markdown 表：正名 | 别名）；
    - `定稿/设定/名册/<正名>.md` 目录：S19 settle 产物（front matter 正名/别名/首现章）。

    同名时目录形态优先（settle 写入的更新鲜）。只读 `名册.md` 会让 v7 原生新书
    （不经迁移、无单表）的实体永远进不了缓存查询面。
    """
    merged: dict[str, dict[str, Any]] = {}
    for entry in _iter_roster_single_table(repo_root):
        merged[entry["name"]] = entry
    for entry in _iter_roster_directory(repo_root):
        merged[entry["name"]] = entry
    yield from merged.values()


def _iter_roster_single_table(repo_root: Path):
    roster = Path(repo_root) / "定稿" / "设定" / "名册.md"
    if not roster.exists():
        return
    for line in _read(roster).splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("| 正名") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[0]:
            yield {"name": cells[0], "aliases": cells[1] if len(cells) > 1 else "", "first_chapter": ""}


def _iter_roster_directory(repo_root: Path):
    roster_dir = Path(repo_root) / "定稿" / "设定" / "名册"
    if not roster_dir.is_dir():
        return
    for path in sorted(roster_dir.glob("*.md")):
        fields, _ = _parse_front_matter(_read(path))
        name = (fields.get("正名") or path.stem).strip()
        if not name:
            continue
        aliases_raw = fields.get("别名", "").strip()
        try:
            aliases = ", ".join(json.loads(aliases_raw)) if aliases_raw else ""
        except (ValueError, TypeError):
            aliases = aliases_raw
        first = fields.get("首现章", "").strip()
        yield {"name": name, "aliases": aliases, "first_chapter": first}


def _iter_summaries(repo_root: Path):
    summary_dir = Path(repo_root) / "定稿" / "记忆" / "章摘要"
    if not summary_dir.exists():
        return
    for path in sorted(summary_dir.glob("*.md")):
        m = re.match(r"(\d+)\.md", path.name)
        if m:
            yield int(m.group(1)), _read(path).strip()


# ---------- 重建与查询 ----------


def rebuild_cache(repo_root: Path) -> dict[str, Any]:
    repo_root = Path(repo_root)
    cache = cache_path(repo_root)
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        cache.unlink()

    book = _parse_book_yaml(repo_root)
    conn = sqlite3.connect(cache)
    try:
        conn.executescript(
            """
            CREATE TABLE chapters (num INTEGER PRIMARY KEY, title TEXT, volume INTEGER,
                                   words INTEGER, file TEXT, body TEXT);
            CREATE TABLE entities (name TEXT PRIMARY KEY, aliases TEXT, first_chapter TEXT NOT NULL DEFAULT '');
            CREATE TABLE summaries (num INTEGER PRIMARY KEY, content TEXT);
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            """
        )
        chapters = list(_iter_chapters(repo_root))
        conn.executemany(
            "INSERT INTO chapters VALUES (?,?,?,?,?,?)",
            [(c["num"], c["title"], c["volume"], c["words"], c["file"], c["body"]) for c in chapters],
        )
        conn.executemany(
            "INSERT INTO entities VALUES (?,?,?)",
            [(e["name"], e["aliases"], e.get("first_chapter", "")) for e in _iter_roster(repo_root)],
        )
        conn.executemany(
            "INSERT INTO summaries VALUES (?,?)",
            [(num, content) for num, content in _iter_summaries(repo_root)],
        )
        conn.executemany(
            "INSERT INTO meta VALUES (?,?)",
            [
                ("rebuilt_at", str(int(__import__("time").time()))),
                ("chapters", str(len(chapters))),
                ("书名", book.get("书名", "")),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return {"chapters": len(chapters), "cache": str(cache)}


def _conn(repo_root: Path) -> sqlite3.Connection:
    path = cache_path(repo_root)
    if not path.exists():
        rebuild_cache(repo_root)
    return sqlite3.connect(path)


def get_chapter(repo_root: Path, num: int) -> Optional[dict[str, Any]]:
    conn = _conn(repo_root)
    try:
        row = conn.execute(
            "SELECT num, title, volume, words, file FROM chapters WHERE num = ?", (num,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {"章号": row[0], "标题": row[1], "卷": row[2], "字数": row[3], "file": row[4]}


def find_entity(repo_root: Path, name: str) -> Optional[dict[str, Any]]:
    """实体查询：正名/别名模糊匹配；首现章来自名册（缺省空串）。"""
    conn = _conn(repo_root)
    try:
        row = conn.execute(
            "SELECT name, aliases, first_chapter FROM entities WHERE name = ? OR aliases LIKE ?",
            (name, f"%{name}%"),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {"name": row[0], "aliases": row[1], "first_chapter": row[2]}


def get_summary(repo_root: Path, num: int) -> Optional[str]:
    conn = _conn(repo_root)
    try:
        row = conn.execute("SELECT content FROM summaries WHERE num = ?", (num,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


# ---------- 验收：删缓存 → 重建 → 快照等价 ----------


def snapshot(repo_root: Path) -> dict[str, Any]:
    """缓存查询面快照：三类查询的全量结果（排序后可比）。"""
    repo_root = Path(repo_root)
    conn = _conn(repo_root)
    try:
        chapters = conn.execute(
            "SELECT num, title, volume, words FROM chapters ORDER BY num"
        ).fetchall()
        entities = conn.execute("SELECT name, aliases FROM entities ORDER BY name").fetchall()
        summaries = conn.execute("SELECT num, content FROM summaries ORDER BY num").fetchall()
    finally:
        conn.close()
    return {"chapters": chapters, "entities": entities, "summaries": summaries}


def verify_rebuild(repo_root: Path) -> dict[str, Any]:
    """验收：删缓存 → 重建 → 查询快照与重建前等价。"""
    repo_root = Path(repo_root)
    before = snapshot(repo_root)
    cache_path(repo_root).unlink(missing_ok=True)
    rebuild_cache(repo_root)
    after = snapshot(repo_root)
    return {"equal": before == after, "before": before, "after": after}


def main() -> None:
    parser = argparse.ArgumentParser(description="v7 story-repo 缓存重建与验收（S17/E2）")
    parser.add_argument("action", choices=["rebuild", "verify", "snapshot"], help="rebuild=重建 verify=删缓存等价验收 snapshot=打印查询快照")
    parser.add_argument("--repo", required=True, help="v7 story-repo 根目录")
    args = parser.parse_args()

    repo = Path(args.repo)
    if args.action == "rebuild":
        report = rebuild_cache(repo)
        print(f"OK v7-cache rebuild chapters={report['chapters']} cache={report['cache']}")
    elif args.action == "verify":
        result = verify_rebuild(repo)
        status = "OK" if result["equal"] else "FAIL"
        print(f"{status} v7-cache verify equal={result['equal']}（删缓存→重建→查询快照等价）")
        raise SystemExit(0 if result["equal"] else 1)
    else:
        print(json.dumps(snapshot(repo), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    main()
