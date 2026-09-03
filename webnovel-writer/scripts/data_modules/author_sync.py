"""author-sync：作者修改留账主入口（webnovel-copilot-300 · M0/T3，流程 F-01）。

机制（0 token 路径）：
1. `git diff HEAD --name-status + --numstat`（含 staged 与未 staged）取工作区变更；
2. 路径规则分类到六域（classify_path），系统域忽略；
3. name-status 推导 change_kind；
4. **内容指纹去重**：事件携带工作区内容 sha1，同 path 同指纹不重复留账
   （提交后 diff 消失亦不重放）；
5. 追加 journal + 按 stale 规则标记（章纲→chapter:NNNN，定版素材→material:…，
   锚点→power-anchor，卷纲→timeline:recheck，条目→promise:…，正文→chapter:N）；
6. migration 守卫：变更文件 >100 时拒绝批量留账，需 confirm_migration 才记一条汇总事件。

红线：只读 git 元数据 + 只追加 作者/journal.jsonl；不改任何被扫描文件。
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

from .author_journal import append_events, read_journal, write_watermark
from .domain_contract import is_story_repo

MIGRATION_THRESHOLD = 100

# 系统域 / 编译产物 / 草稿区 / 治理层自产文件：作者事件不覆盖
# （journal/watermark/stale 是 author-sync 自己写的，重扫会自指污染事件流）
IGNORED_PREFIXES: tuple[str, ...] = (
    ".webnovel/", ".story-system/", ".cache/", ".loom/", "工作区/", ".git/",
    "作者/journal.jsonl", "作者/.watermark", ".webnovel/stale.json",
)

_DOMAIN_RULES: tuple[tuple[str, str], ...] = (
    ("设定/力量锚点.yaml", "战力"),
    ("大纲/regen/总纲/", "总纲"),
    ("大纲/总纲.md", "总纲"),
    ("大纲/卷纲/", "卷纲"),
    ("大纲/章纲/", "章纲"),
    ("大纲/条目/", "条目"),
    ("素材/", "素材"),
    ("设定/", "设定"),
    ("定稿/正文/", "正文"),
    ("文风/", "文风"),
)

_CHAPTER_NUM_RE = re.compile(r"(\d{1,4})")


def _normalize_path(path: str) -> str:
    """统一分隔符并剥离 ./ 前缀（注意：不能按字符集 lstrip，否则 .webnovel 会变成 webnovel）。"""
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def classify_path(path: str) -> str:
    """路径 → 六域（0 token 规则表）。"""
    normalized = _normalize_path(path)
    for prefix, domain in _DOMAIN_RULES:
        if normalized == prefix or normalized.startswith(prefix):
            return domain
    return "其他"


def change_kind_for(name_status: str) -> str:
    code = (name_status or "M").strip()
    if code.startswith("A"):
        return "add"
    if code.startswith("D"):
        return "delete"
    if code.startswith("R") or code.startswith("C"):
        return "structure"
    return "content"


def _git(root: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _repo_toplevel_ok(root: Path) -> bool:
    """root 自身必须是 git 仓库根（防止误扫父仓库/相邻仓库）。"""
    code, out, _ = _git(root, "rev-parse", "--show-toplevel")
    if code != 0:
        return False
    try:
        return Path(out.strip()).resolve() == root.resolve()
    except OSError:
        return False


def _is_ignored(path: str) -> bool:
    normalized = _normalize_path(path)
    return any(normalized.startswith(prefix) for prefix in IGNORED_PREFIXES)


def _content_sha1(root: Path, path: str, status: str) -> str:
    if status.startswith("D"):
        return "deleted"
    target = root / path
    if not target.is_file():
        return "missing"
    digest = hashlib.sha1()
    with target.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_changes(root: Path) -> list[dict[str, Any]]:
    """变更来源 = `git status --porcelain`（含未跟踪新文件——作者新建是常态）。

    numstat 取自 `git diff HEAD`（仅跟踪文件）；未跟踪新文件按整文件行数计 ins。
    """
    _, num_out, _ = _git(root, "diff", "HEAD", "--numstat", "--no-renames")
    numstat: dict[str, tuple[int, int]] = {}
    for line in num_out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            ins, dele, path = parts
            try:
                numstat[path] = (int(ins) if ins != "-" else 0, int(dele) if dele != "-" else 0)
            except ValueError:
                numstat[path] = (0, 0)

    _, status_out, _ = _git(root, "-c", "core.quotepath=false", "status", "--porcelain", "--untracked-files=all")
    changes: list[dict[str, Any]] = []
    for line in status_out.splitlines():
        if len(line) < 4:
            continue
        xy, path = line[:2], line[3:].strip().strip('"')
        if not path:
            continue
        status = _status_code(xy, path)
        if status is None:
            continue
        # 中文路径在 quotepath=off 下原样输出；仅剥离外层引号（安全名场景）
        path = path.strip('"')
        if path in numstat:
            ins, dele = numstat[path]
        elif status.startswith("A"):
            ins, dele = _count_lines(root, path), 0
        else:
            ins, dele = 0, 0
        changes.append({"path": path, "status": status, "ins": ins, "del": dele})
    return changes


def _status_code(xy: str, path: str) -> str | None:
    """porcelain XY → 语义状态码（A/D/R/M）；忽略未合并冲突态。"""
    work, index = xy[1], xy[0]
    if work == "?" or index == "?":
        return "A"  # 未跟踪新文件（-uall 已展开到文件级）
    if xy.strip(" ?!") == "":
        return None
    for code in (work, index):
        if code in "ADRC":
            return code
    return "M"


def _count_lines(root: Path, path: str) -> int:
    target = root / path
    if target.is_file():
        try:
            return len(target.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            return 0
    return 0


def _stale_for(domain: str, path: str) -> dict[str, Any] | None:
    normalized = path.replace("\\", "/")
    if domain == "章纲":
        match = _CHAPTER_NUM_RE.search(Path(normalized).stem)
        if match:
            return {"target": f"chapter:{match.group(1)}", "reason": "章纲被作者修改", "impact": [f"context-stale:{match.group(1)}"]}
    if domain == "素材" and "/定版/" in normalized:
        return {"target": f"material:{normalized}", "reason": "定版素材被修改", "impact": ["引用章反查"]}
    if domain == "战力":
        return {"target": "power-anchor", "reason": "战力锚点被修改", "impact": ["战例对账"]}
    if domain == "卷纲":
        return {"target": "timeline:recheck", "reason": "卷纲/时间线被修改", "impact": ["时间线重校验"]}
    if domain == "条目":
        return {"target": f"promise:{Path(normalized).stem}", "reason": "承诺条目被修改", "impact": ["账本同步检查"]}
    if domain == "正文":
        match = _CHAPTER_NUM_RE.search(Path(normalized).stem)
        if match:
            return {"target": f"chapter:{match.group(1)}", "reason": "已定稿正文被作者修改", "impact": [f"fact-recheck:{match.group(1)}"]}
    return None


def run_author_sync(
    project_root: str | Path,
    *,
    confirm_migration: bool = False,
) -> dict[str, Any]:
    """扫描→分类→留账→stale。返回结构化报告。"""
    from .author_journal import mark_stale

    root = Path(project_root)
    if not _repo_toplevel_ok(root):
        return {
            "ok": False,
            "error": "not a git repo (or not repo toplevel)",
            "new_events": 0,
        }

    changes = _collect_changes(root)
    ignored = 0
    tracked: list[dict[str, Any]] = []
    for change in changes:
        if _is_ignored(change["path"]):
            ignored += 1
        else:
            tracked.append(change)

    # migration 守卫
    if len(tracked) > MIGRATION_THRESHOLD:
        if not confirm_migration:
            return {
                "ok": True,
                "migration_guard": True,
                "pending_files": len(tracked),
                "new_events": 0,
                "hint": f"{len(tracked)} 个文件变更超出批量阈值（{MIGRATION_THRESHOLD}），疑似迁移/重排；确认后用 --confirm-migration 记录为一条汇总事件。",
            }
        event = {
            "actor": "author",
            "action": "edit",
            "domain": "其他",
            "path": "(bulk)",
            "change_kind": "structure",
            "diff_stat": {"files": len(tracked)},
            "summary": f"批量变更 {len(tracked)} 个文件（migration 确认）",
            "impact": ["migration"],
        }
        append_events(root, [event])
        return {
            "ok": True,
            "migration_guard": True,
            "confirmed": True,
            "pending_files": len(tracked),
            "new_events": 1,
        }

    # 指纹去重：该 path 最近一次事件的工作区内容指纹
    history = read_journal(root)
    last_sha_by_path: dict[str, str] = {}
    for event in history:
        path = str(event.get("path") or "")
        sha = str(event.get("content_sha1") or "")
        if path and sha:
            last_sha_by_path[path] = sha

    new_events: list[dict[str, Any]] = []
    stale_marks: list[dict[str, Any]] = []
    for change in tracked:
        path = change["path"]
        domain = classify_path(path)
        sha = _content_sha1(root, path, change["status"])
        if last_sha_by_path.get(path) == sha:
            continue  # 同内容已留账
        event = {
            "actor": "author",
            "action": "edit",
            "domain": domain,
            "path": path,
            "change_kind": change_kind_for(change["status"]),
            "diff_stat": {"ins": change["ins"], "del": change["del"]},
            "summary": "",
            "impact": [],
            "content_sha1": sha,
        }
        new_events.append(event)
        stale = _stale_for(domain, path)
        if stale:
            stale_marks.append(stale)

    if new_events:
        append_events(root, new_events)
        for mark in stale_marks:
            mark_stale(
                root,
                target=mark["target"],
                reason=mark["reason"],
                impact=mark["impact"],
            )
        write_watermark(root, len(history) + len(new_events))
    else:
        write_watermark(root, len(history))

    return {
        "ok": True,
        "project_root": str(root),
        "story_repo": is_story_repo(root),
        "scanned": len(changes),
        "ignored": ignored,
        "tracked": len(tracked),
        "new_events": len(new_events),
        "stale_marks": stale_marks,
        "migration_guard": False,
    }


def format_impact_summary(report: dict[str, Any]) -> str:
    """作者语言的影响摘要（F-01 第 5 步；0 token，≤10 行）。

    输入为 run_author_sync 的报告；new_events=0 时返回空串（会话不注入噪音）。
    """
    if not report.get("ok") or not report.get("new_events"):
        return ""
    marks = report.get("stale_marks") or []
    targets: list[str] = []
    for mark in marks:
        target = str(mark.get("target") or "")
        if target and target not in targets:
            targets.append(target)
    lines: list[str] = [f"作者已改 {report.get('new_events')} 处（上次会话后）："]
    for target in targets[:8]:
        reason = next(str(m.get("reason")) for m in marks if m.get("target") == target)
        lines.append(f"- {reason}：{target}")
    if report.get("migration_guard") and report.get("confirmed"):
        lines.append("- 批量变更已按 migration 记录")
    if len(targets) > 8:
        lines.append(f"- …另有 {len(targets) - 8} 项影响标记（详见 journal）")
    return "\n".join(lines)


def format_sync_report(report: dict[str, Any]) -> str:
    """文本输出。零事件时返回空串（hook 静默）；有事件时 = 一行技术摘要 + stale 清单。"""
    if not report.get("ok"):
        return f"ERROR author-sync: {report.get('error')}"
    if report.get("migration_guard") and not report.get("confirmed"):
        return (
            f"WARN author-sync: {report.get('hint')}\n"
            "确认是迁移/重排后运行 --confirm-migration。"
        )
    if not report.get("new_events"):
        return ""
    lines = [
        f"OK author-sync: +{report.get('new_events', 0)} events "
        f"(scanned={report.get('scanned', 0)}, ignored={report.get('ignored', 0)}, tracked={report.get('tracked', 0)})",
    ]
    impact = format_impact_summary(report)
    if impact:
        lines.append(impact)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="作者修改留账（author-sync，0 token 路径）")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--confirm-migration", action="store_true", help="批量变更（>100 文件）确认记录为汇总事件")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    report = run_author_sync(args.project_root, confirm_migration=args.confirm_migration)
    if args.format == "json":
        print(_json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_sync_report(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
