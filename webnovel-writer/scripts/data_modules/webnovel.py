#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
webnovel 统一入口（面向 skills / agents 的稳定 CLI）

设计目标：
- 只有一个入口命令，避免到处拼 `python -m data_modules.xxx ...` 导致参数位置/引号/路径炸裂。
- 自动解析正确的 book project_root（包含 `.webnovel/state.json` 的目录）。
- 所有写入类命令在解析到 project_root 后，统一前置 `--project-root` 传给具体模块。

典型用法（推荐，不依赖 PYTHONPATH / 不要求 cd）：
  python "<SCRIPTS_DIR>/webnovel.py" preflight
  python "<SCRIPTS_DIR>/webnovel.py" where
  python "<SCRIPTS_DIR>/webnovel.py" use "<PROJECT_ROOT>"
  python "<SCRIPTS_DIR>/webnovel.py" --project-root "<PROJECT_ROOT>" index stats
  python "<SCRIPTS_DIR>/webnovel.py" --project-root "<PROJECT_ROOT>" state process-chapter --chapter 100 --data @payload.json
  python "<SCRIPTS_DIR>/webnovel.py" --project-root "<PROJECT_ROOT>" extract-context --chapter 100 --format json

也支持（不推荐，容易踩 PYTHONPATH/cd/参数顺序坑）：
  python -m data_modules.webnovel where
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from runtime_compat import enable_windows_utf8_stdio, normalize_windows_path
from project_locator import resolve_project_root, write_current_project_pointer, update_global_registry_current_project

from .story_runtime_health import build_story_runtime_health


if sys.platform == "win32":
    enable_windows_utf8_stdio(skip_in_pytest=True)


def _scripts_dir() -> Path:
    # data_modules/webnovel.py -> data_modules -> scripts
    return Path(__file__).resolve().parent.parent


def _resolve_root(explicit_project_root: Optional[str]) -> Path:
    # 允许显式传入工作区根目录或书项目根目录
    raw = explicit_project_root
    if raw:
        return resolve_project_root(raw)
    return resolve_project_root()


def _strip_project_root_args(argv: list[str]) -> list[str]:
    """
    下游工具统一由本入口注入 `--project-root`，避免重复传参导致 argparse 报错/歧义。
    """
    out: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--project-root":
            i += 2
            continue
        if tok.startswith("--project-root="):
            i += 1
            continue
        out.append(tok)
        i += 1
    return out


PASSTHROUGH_TOOLS = {
    "index",
    "state",
    "rag",
    "style",
    "entity",
    "context",
    "memory",
    "migrate",
    "status",
    "update-state",
    "backup",
    "archive",
    "init",
    "story-system",
    "memory-contract",
    "project-memory",
}


def _passthrough_tail(argv: list[str], tool: str) -> list[str]:
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--project-root":
            i += 2
            continue
        if token.startswith("--project-root="):
            i += 1
            continue
        if token == tool:
            return list(argv[i + 1 :])
        i += 1
    return []


def _run_data_module(module: str, argv: list[str]) -> int:
    """
    Import `data_modules.<module>` and call its main(), while isolating sys.argv.
    """
    mod = importlib.import_module(f"data_modules.{module}")
    main = getattr(mod, "main", None)
    if not callable(main):
        raise RuntimeError(f"data_modules.{module} 缺少可调用的 main()")

    old_argv = sys.argv
    try:
        sys.argv = [f"data_modules.{module}"] + argv
        try:
            main()
            return 0
        except SystemExit as e:
            return int(e.code or 0)
    finally:
        sys.argv = old_argv


def _run_script(script_name: str, argv: list[str]) -> int:
    """
    Run a script under `.claude/scripts/` via a subprocess.

    用途：兼容没有 main() 的脚本。
    """
    script_path = _scripts_dir() / script_name
    if not script_path.is_file():
        raise FileNotFoundError(f"未找到脚本: {script_path}")
    proc = subprocess.run([sys.executable, str(script_path), *argv])
    return int(proc.returncode or 0)


def cmd_where(args: argparse.Namespace) -> int:
    try:
        root = _resolve_root(args.project_root)
    except FileNotFoundError as exc:
        print(_project_root_diagnostic(args.project_root, exc), file=sys.stderr)
        return 1
    print(str(root))
    return 0


def _resolve_root_lenient(raw: str) -> Path:
    """宽松解析：v6 项目走 _resolve_root；纯 v7 story-repo（book.yaml）直接用给定目录。"""
    try:
        return _resolve_root(raw)
    except FileNotFoundError:
        candidate = Path(raw)
        if candidate.is_dir():
            from data_modules import domain_contract

            if domain_contract.is_story_repo(candidate):
                return candidate
        raise


def cmd_freeze(args: argparse.Namespace) -> int:
    """卷收尾冻结与 retcon 裁决（T10）。"""
    from data_modules import freeze_manager

    root = _resolve_root_lenient(args.project_root)
    argv = [args.action, "--volume", str(args.volume), "--project-root", str(root), "--format", args.format]
    if args.force:
        argv.append("--force")
    if args.choice:
        argv.extend(["--choice", args.choice])
    if args.reason:
        argv.extend(["--reason", args.reason])
    if args.affected:
        argv.extend(["--affected", args.affected])
    return freeze_manager.main(argv)


def cmd_timeline(args: argparse.Namespace) -> int:
    """卷纲时间线视图（T9）：build 导出 / sync 反向回写（默认 dry-run）。"""
    from data_modules import timeline_view

    root = _resolve_root_lenient(args.project_root)
    argv = [args.action, "--volume", str(args.volume), "--project-root", str(root), "--format", args.format]
    if args.apply:
        argv.append("--apply")
    return timeline_view.main(argv)


def cmd_chapter_batch(args: argparse.Namespace) -> int:
    """章纲批量（T8）：confirm 一次确认一批。"""
    from data_modules import chapter_outline_batch

    root = _resolve_root_lenient(args.project_root)
    return chapter_outline_batch.main(["confirm", "--chapters", args.chapters, "--project-root", str(root), "--format", args.format])


def cmd_regen(args: argparse.Namespace) -> int:
    """regen 画廊（T7）。"""
    from data_modules import regen_gallery

    root = _resolve_root_lenient(args.project_root)
    argv = [args.action, "--domain", args.domain, "--key", args.key, "--project-root", str(root), "--format", args.format]
    if args.version is not None:
        argv.extend(["--version", str(args.version)])
    if args.against is not None:
        argv.extend(["--against", str(args.against)])
    if args.content_file:
        argv.extend(["--content-file", args.content_file])
    if args.force:
        argv.append("--force")
    return regen_gallery.main(argv)


def cmd_zones(args: argparse.Namespace) -> int:
    """总纲三区（T6）：migrate 自动分区 / show 状态。"""
    from data_modules import master_outline_zones

    root = _resolve_root_lenient(args.project_root)
    argv = [args.action, "--project-root", str(root), "--format", args.format]
    if args.dry_run:
        argv.append("--dry-run")
    return master_outline_zones.main(argv)


def cmd_impact(args: argparse.Namespace) -> int:
    """影响反查（T5）：对指定文件路径输出受影响面与三选项建议（只读）。"""
    from data_modules import impact_analyzer

    root = _resolve_root_lenient(args.project_root)
    return impact_analyzer.main(["--path", args.path, "--project-root", str(root), "--format", args.format])


def cmd_author_sync(args: argparse.Namespace) -> int:
    """author-sync：作者修改留账（T3/T4，解析放宽同 domains）。"""
    from data_modules import author_sync

    root = _resolve_root_lenient(args.project_root)
    argv = ["--project-root", str(root), "--format", args.format]
    if args.confirm_migration:
        argv.append("--confirm-migration")
    return author_sync.main(argv)


def cmd_domains(args: argparse.Namespace) -> int:
    """六域目录契约（webnovel-copilot-300 T1）：init 幂等建骨架 / check 只读体检。

    解析放宽：纯 v7 story-repo（book.yaml、无 .webnovel/state.json）直接按给定目录操作。
    """
    from data_modules import domain_contract

    root = _resolve_root_lenient(args.project_root)
    argv = [args.action, "--project-root", str(root), "--format", args.format]
    return domain_contract.main(argv)


def cmd_materials(args: argparse.Namespace) -> int:
    """素材工作台（webnovel-copilot-300 M2/T11-T14，流程 F-05/F-06）。

    解析放宽同 domains：纯 v7 story-repo 直接按给定目录操作。
    action 专属参数由 material_store.main 自行解析，这里只转发。
    """
    from data_modules import material_store

    root = _resolve_root_lenient(args.project_root)
    rest = list(getattr(args, "material_args", []) or [])
    if rest[:1] == ["--"]:
        rest = rest[1:]
    argv = [args.action, *rest, "--project-root", str(root)]
    if "--format" not in rest:
        argv.extend(["--format", args.format])
    return material_store.main(argv)


def cmd_style_domain(args: argparse.Namespace) -> int:
    """文风域数据面（webnovel-copilot-300 M3/T15）：宪法迁移 / 指纹 / 金句库。"""
    from data_modules import style_domain

    root = _resolve_root_lenient(args.project_root)
    argv = [args.action, "--project-root", str(root), "--format", args.format]
    if args.action == "fingerprint" and args.chapter:
        argv.extend(["--chapter", str(args.chapter)])
    if args.action == "golden-add":
        argv.extend(["--chapter", str(args.chapter or 0), "--text", args.text, "--note", args.note])
    if args.action == "golden-feed":
        argv.extend(["--id", args.id])
    return style_domain.main(argv)


def cmd_learn(args: argparse.Namespace) -> int:
    """学习闭环（webnovel-copilot-300 M3/T16，F-12）：learn --from-journal / apply / show。"""
    from data_modules import author_model

    root = _resolve_root_lenient(args.project_root)
    argv = [args.action, "--project-root", str(root), "--format", args.format]
    if args.action == "learn":
        if args.from_journal:
            argv.append("--from-journal")
        if args.volume:
            argv.extend(["--volume", str(args.volume)])
    if args.action == "apply" and args.suggestion:
        argv.extend(["--suggestion", args.suggestion])
    return author_model.main(argv)


def cmd_power(args: argparse.Namespace) -> int:
    """战力域（webnovel-copilot-300 M4/T18-T19，F-09）：锚点抽取/校验/战例/通胀/power-check。"""
    from data_modules import power_anchor

    root = _resolve_root_lenient(args.project_root)
    rest = list(getattr(args, "power_args", []) or [])
    if rest[:1] == ["--"]:
        rest = rest[1:]
    argv = [args.action, *rest, "--project-root", str(root)]
    if "--format" not in rest:
        argv.extend(["--format", args.format])
    return power_anchor.main(argv)


def cmd_forge(args: argparse.Namespace) -> int:
    """设定工坊（webnovel-copilot-300 M4/T20，F-08）：prepare/save/adopt/confirm/list。"""
    from data_modules import setting_forge

    root = _resolve_root_lenient(args.project_root)
    argv = [args.action, "--project-root", str(root), "--format", args.format]
    if args.category:
        argv.extend(["--category", args.category])
    if args.file:
        argv.extend(["--file", args.file])
    if args.action == "adopt":
        if args.version:
            argv.extend(["--version", str(args.version)])
        if args.proposal:
            argv.extend(["--proposal", str(args.proposal)])
    if args.action == "confirm" and args.draft:
        argv.extend(["--draft", args.draft])
    return setting_forge.main(argv)


def _project_root_diagnostic(
    explicit_project_root: Optional[str], exc: FileNotFoundError
) -> str:
    if explicit_project_root:
        return (
            "未找到有效书项目根目录（需要包含 .webnovel/state.json）: "
            f"{explicit_project_root}\n"
            f"detail: {exc}"
        )
    return (
        "当前工作区还没有激活的书项目（未找到 .webnovel/state.json）。\n"
        "请先运行 webnovel init 创建项目，或运行 webnovel use <project_root> 绑定已有书项目。\n"
        f"detail: {exc}"
    )


def _build_preflight_report(explicit_project_root: Optional[str]) -> dict:
    scripts_dir = _scripts_dir().resolve()
    plugin_root = scripts_dir.parent
    skill_root = plugin_root / "skills" / "webnovel-write"
    entry_script = scripts_dir / "webnovel.py"
    extract_script = scripts_dir / "extract_chapter_context.py"

    checks: list[dict[str, object]] = [
        {"name": "scripts_dir", "ok": scripts_dir.is_dir(), "path": str(scripts_dir)},
        {"name": "entry_script", "ok": entry_script.is_file(), "path": str(entry_script)},
        {"name": "extract_context_script", "ok": extract_script.is_file(), "path": str(extract_script)},
        {"name": "skill_root", "ok": skill_root.is_dir(), "path": str(skill_root)},
    ]

    project_root = ""
    project_root_error = ""
    story_runtime: dict = {}
    try:
        resolved_root = _resolve_root(explicit_project_root)
        project_root = str(resolved_root)
        checks.append({"name": "project_root", "ok": True, "path": project_root})
        story_runtime = build_story_runtime_health(resolved_root)
    except FileNotFoundError as exc:
        project_root_error = _project_root_diagnostic(explicit_project_root, exc)
        checks.append(
            {
                "name": "project_root",
                "ok": False,
                "path": explicit_project_root or "",
                "error": project_root_error,
            }
        )
    except Exception as exc:
        project_root_error = str(exc)
        checks.append({"name": "project_root", "ok": False, "path": explicit_project_root or "", "error": project_root_error})

    return {
        "ok": all(bool(item["ok"]) for item in checks),
        "project_root": project_root,
        "scripts_dir": str(scripts_dir),
        "skill_root": str(skill_root),
        "checks": checks,
        "project_root_error": project_root_error,
        "story_runtime": story_runtime,
    }


def cmd_preflight(args: argparse.Namespace) -> int:
    report = _build_preflight_report(args.project_root)
    if args.format == "json" and not getattr(args, "all_flag", False):
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    for item in report["checks"]:
        status = "OK" if item["ok"] else "ERROR"
        path = item.get("path") or ""
        print(f"{status} {item['name']}: {path}")
        if item.get("error"):
            print(f"  detail: {item['error']}")
    story_runtime = report.get("story_runtime") or {}
    if story_runtime:
        print(
            "INFO story_runtime: "
            f"chapter={story_runtime.get('chapter')} "
            f"mainline_ready={story_runtime.get('mainline_ready')} "
            f"latest_commit_status={story_runtime.get('latest_commit_status')}"
        )

    placeholders: list[dict[str, Any]] = []
    if getattr(args, "all_flag", False):
        # S9/D2：三查合一——preflight + where + placeholder-scan 一次往返完成
        from project_locator import resolve_project_root

        try:
            root = resolve_project_root(Path(args.project_root))
        except Exception:
            root = None
        print(f"PROJECT_ROOT={root or args.project_root}")

        from .placeholder_scanner import scan_placeholders

        placeholders = scan_placeholders(args.project_root)
        if placeholders:
            print(f"PLACEHOLDER count={len(placeholders)}")
            for item in placeholders[:10]:
                location = f"{item.get('file')}:{item.get('line')}" if item.get("line") else str(item.get("file"))
                print(f"  {location}: {str(item.get('pattern') or '')[:60]}")
        else:
            print("PLACEHOLDER count=0")
    return 0 if report["ok"] and not placeholders else 1


def cmd_project_status(args: argparse.Namespace) -> int:
    from .project_status import build_project_status, format_project_status

    try:
        root: Path | str | None = _resolve_root(args.project_root)
    except FileNotFoundError:
        root = args.project_root or None
    report = build_project_status(root, chapter=args.chapter)
    print(format_project_status(report, args.format))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import build_doctor_report, format_doctor_report

    preflight_report = _build_preflight_report(args.project_root)
    root: Path | str | None = preflight_report.get("project_root") or args.project_root or None
    report = build_doctor_report(
        root,
        chapter=args.chapter,
        deep=bool(args.deep),
        preflight_report=preflight_report,
    )
    print(format_doctor_report(report, args.format))
    return 0 if report.get("ok") else 1


def cmd_timeline_check(args: argparse.Namespace) -> int:
    from .timeline_check import check_timeline, format_timeline_report

    root = _resolve_root(args.project_root)
    report = check_timeline(root, args.volume)
    print(format_timeline_report(report, args.format))
    return 0 if report.get("ok") else 1


def cmd_meter(args: argparse.Namespace) -> int:
    from .chapter_meter import (
        aggregate_usage,
        format_usage_line,
        read_marker,
        start_meter,
        stop_meter,
    )

    root = _resolve_root(args.project_root)
    db_path = Path(args.db) if getattr(args, "db", "") else None
    if args.meter_action == "start":
        marker = start_meter(root, chapter=args.chapter, db_path=db_path, session=args.session or None)
        print(
            f"OK chapter-meter start chapter={marker['chapter']}"
            f" session={marker['session_id'] or '(unresolved)'}"
            f" anchor={marker['started_at']}"
        )
        return 0
    marker = read_marker(root)
    if marker is None:
        print("SKIP chapter-meter: no open marker (.webnovel/tmp/chapter_meter.json)")
        return 0
    if args.meter_action == "stop":
        print(stop_meter(root, db_path=db_path))
        return 0
    print(format_usage_line(marker, aggregate_usage(root, marker, db_path=db_path)))
    return 0


def cmd_setting_read(args: argparse.Namespace) -> int:
    """S3/C3 L2：按需读取设定文件原文（默认全文，--max-chars 可截）。"""
    from .config import DataModulesConfig
    from .settings_digest import _find_setting_path

    root = _resolve_root(args.project_root)
    cfg = DataModulesConfig.from_project_root(root)
    source = _find_setting_path(cfg.settings_dir, args.name)
    if source is None:
        print(f"ERROR setting-read: 未找到设定文件（keyword={args.name}）")
        return 1
    text = source.read_text(encoding="utf-8")
    max_chars = int(getattr(args, "max_chars", 0) or 0)
    if max_chars > 0 and len(text) > max_chars:
        marker = "\n…（截断）"
        text = text[: max(0, max_chars - len(marker))] + marker
    print(text)
    return 0


def cmd_write_gate(args: argparse.Namespace) -> int:
    from .write_gates import (
        externalize_gate_report,
        format_gate_compact,
        format_gate_report,
        run_write_gate,
    )

    root = _resolve_root(args.project_root)
    report = run_write_gate(root, chapter=args.chapter, stage=args.stage)
    externalize_gate_report(root, report)
    if args.format == "json":
        print(format_gate_report(report, "json"))
    elif args.format == "text":
        print(format_gate_report(report, "text"))
    else:
        print(format_gate_compact(report))
    return 0 if report.get("ok") else 1


def cmd_projections(args: argparse.Namespace) -> int:
    from .projections import format_projection_report, replay_projections, retry_projection

    root = _resolve_root(args.project_root)
    if args.projection_action == "retry":
        report = retry_projection(root, chapter=args.chapter)
    else:
        report = replay_projections(
            root,
            start_chapter=args.from_chapter,
            end_chapter=args.to_chapter,
        )
    print(format_projection_report(report, args.format))
    return 0 if report.get("ok") else 1


def cmd_user_report(args: argparse.Namespace) -> int:
    from .user_report import build_user_report, format_user_report

    root = _resolve_root(args.project_root)
    report = build_user_report(
        root,
        stage=args.stage,
        chapter=args.chapter,
        volume=args.volume,
    )
    print(format_user_report(report, args.format))
    return 0


def cmd_run_ledger(args: argparse.Namespace) -> int:
    from .run_ledger import (
        build_write_resume_plan,
        format_resume_plan,
        read_subagent_runs,
        record_subagent_run,
        record_write_step,
    )

    root = _resolve_root(args.project_root)
    if args.ledger_action == "record-write-step":
        try:
            inputs = json.loads(args.inputs_json)
            outputs = json.loads(args.outputs_json)
            problems = json.loads(args.problems_json)
            auto_handled = json.loads(args.auto_handled_json)
        except json.JSONDecodeError as exc:
            print(f"ledger JSON 参数不合法: {exc}", file=sys.stderr)
            return 2
        if not isinstance(inputs, dict) or not isinstance(outputs, dict):
            print("inputs-json / outputs-json 必须是 JSON object", file=sys.stderr)
            return 2
        if not isinstance(problems, list) or not isinstance(auto_handled, list):
            print("problems-json / auto-handled-json 必须是 JSON list", file=sys.stderr)
            return 2
        entry = record_write_step(
            root,
            chapter=args.chapter,
            step=args.step,
            status=args.status,
            mode=args.mode,
            inputs={str(key): str(value) for key, value in inputs.items()},
            outputs={str(key): str(value) for key, value in outputs.items()},
            problems=[str(item) for item in problems],
            auto_handled=[str(item) for item in auto_handled],
            duration_ms=args.duration_ms,
        )
        if args.format == "json":
            print(json.dumps(entry, ensure_ascii=False, indent=2))
        else:
            print(f"{entry['step']}: {entry['status']}")
        return 0
    if args.ledger_action == "record-write-steps":
        # S9/D2：批量记账——崩溃粒度由 run-log --append 保证，ledger 在收尾/阶段末一次冲账
        try:
            steps = json.loads(args.steps_json)
        except json.JSONDecodeError as exc:
            print(f"ledger JSON 参数不合法: {exc}", file=sys.stderr)
            return 2
        if not isinstance(steps, list) or not steps:
            print("steps-json 必须是非空 JSON list", file=sys.stderr)
            return 2
        recorded = 0
        for item in steps:
            if not isinstance(item, dict):
                print("steps-json 的每一项必须是 object", file=sys.stderr)
                return 2
            try:
                record_write_step(
                    root,
                    chapter=args.chapter,
                    step=str(item.get("step")),
                    status=str(item.get("status") or "completed"),
                    mode=str(item.get("mode") or args.mode),
                    problems=[str(p) for p in (item.get("problems") or [])],
                    auto_handled=[str(p) for p in (item.get("auto_handled") or [])],
                    duration_ms=int(item.get("duration_ms") or 0),
                )
                recorded += 1
            except (ValueError, TypeError) as exc:
                print(f"步骤 {item.get('step')!r} 记账失败: {exc}", file=sys.stderr)
                return 2
        print(f"OK run-ledger record-write-steps count={recorded}")
        return 0
    if args.ledger_action == "record-subagent":
        try:
            problems = json.loads(args.problems_json)
            auto_handled = json.loads(args.auto_handled_json)
            outputs = json.loads(args.outputs_json)
        except json.JSONDecodeError as exc:
            print(f"subagent JSON 参数不合法: {exc}", file=sys.stderr)
            return 2
        if not isinstance(problems, list) or not isinstance(auto_handled, list) or not isinstance(outputs, list):
            print("problems-json / auto-handled-json / outputs-json 必须是 JSON list", file=sys.stderr)
            return 2
        entry = record_subagent_run(
            root,
            run_id=args.run_id,
            name=args.name,
            user_label=args.user_label,
            status=args.status,
            command=args.command,
            stage=args.stage,
            chapter=args.chapter,
            volume=args.volume,
            problems=[str(item) for item in problems],
            auto_handled=[str(item) for item in auto_handled],
            needs_user_action=args.needs_user_action,
            duration_ms=args.duration_ms,
            outputs=[str(item) for item in outputs],
        )
        if args.format == "json":
            print(json.dumps(entry, ensure_ascii=False, indent=2))
        else:
            print(f"{entry['name']}: {entry['status']}")
        return 0
    if args.ledger_action == "get-subagent-runs":
        entries = read_subagent_runs(
            root,
            command=args.command or None,
            stage=args.stage or None,
            chapter=args.chapter,
            latest_only=args.latest_only,
        )
        if args.format == "json":
            print(json.dumps(entries, ensure_ascii=False, indent=2))
        else:
            for entry in entries:
                print(f"{entry.get('name')}: {entry.get('status')}")
        return 0
    if args.ledger_action == "write-resume":
        report = build_write_resume_plan(
            root,
            chapter=args.chapter,
            mode=args.mode,
        )
        print(format_resume_plan(report, args.format))
        return 0
    return 2


def cmd_run_log(args: argparse.Namespace) -> int:
    from .run_logger import write_run_log

    try:
        root = _resolve_root(args.project_root)
    except FileNotFoundError:
        root = normalize_windows_path(args.project_root).expanduser()
        try:
            root = root.resolve()
        except Exception:
            root = root
    try:
        payload = json.loads(args.payload_json)
    except json.JSONDecodeError as exc:
        print(f"payload-json 不是合法 JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("payload-json 必须是 JSON object", file=sys.stderr)
        return 2
    result = write_run_log(root, event=args.event, payload=payload, append=args.append)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["path"])
    return 0


def cmd_use(args: argparse.Namespace) -> int:
    project_root = normalize_windows_path(args.project_root).expanduser()
    try:
        project_root = project_root.resolve()
    except Exception as exc:
        import sys
        print(f"⚠️ path.resolve() 失败 ({project_root}): {exc}", file=sys.stderr)
        project_root = project_root

    workspace_root: Optional[Path] = None
    if args.workspace_root:
        workspace_root = normalize_windows_path(args.workspace_root).expanduser()
        try:
            workspace_root = workspace_root.resolve()
        except Exception as exc:
            import sys
            print(f"⚠️ path.resolve() 失败 ({workspace_root}): {exc}", file=sys.stderr)
            workspace_root = workspace_root

    # 1) 写入工作区指针（若工作区内存在 `.claude/`）
    pointer_file = write_current_project_pointer(project_root, workspace_root=workspace_root)
    if pointer_file is not None:
        print(f"workspace pointer: {pointer_file}")
    else:
        print("workspace pointer: (skipped)")

    # 2) 写入用户级 registry（保证全局安装/空上下文可恢复）
    reg_path = update_global_registry_current_project(workspace_root=workspace_root, project_root=project_root)
    if reg_path is not None:
        print(f"global registry: {reg_path}")
    else:
        print("global registry: (skipped)")

    return 0


_LAST_ARGS = None


def main() -> None:
    """S10/D3：进程内 stdout 捕获，超过阈值（默认 20k 字符）自动外置化。

    `_run_script` 子进程转发类命令（extract-context / memory-contract /
    story-system 等）不经此通道——它们的 stdout 由子进程直接写终端；
    这些入口在 S1-S9 已完成紧凑化。`WEBNOVEL_OUTPUT_EXTERNALIZE=0` 整体关闭。
    """
    import contextlib
    import io

    buf = io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf):
            _main_impl()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 0

    from .output_guard import externalize_if_needed

    root = None
    try:
        pr = getattr(_LAST_ARGS, "project_root", None)
        root = _resolve_root(pr)
    except Exception:
        root = None
    print(externalize_if_needed(buf.getvalue(), tool=getattr(_LAST_ARGS, "tool", "cli"), project_root=root))
    raise SystemExit(code)


def _main_impl() -> None:
    global _LAST_ARGS
    parser = argparse.ArgumentParser(description="webnovel unified CLI")
    parser.add_argument("--project-root", help="书项目根目录或工作区根目录（可选，默认自动检测）")

    sub = parser.add_subparsers(dest="tool", required=True)

    p_where = sub.add_parser("where", help="打印解析出的 project_root")
    p_where.set_defaults(func=cmd_where)

    p_preflight = sub.add_parser("preflight", help="校验统一 CLI 运行环境与 project_root")
    p_preflight.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    p_preflight.add_argument(
        "--all",
        dest="all_flag",
        action="store_true",
        help="三查合一：preflight + where（PROJECT_ROOT=） + placeholder-scan，占位符存在时退出码 1",
    )
    p_preflight.set_defaults(func=cmd_preflight)

    p_project_status = sub.add_parser("project-status", help="输出机器可读的项目短状态")
    p_project_status.add_argument("--chapter", type=int, default=None, help="目标章节号")
    p_project_status.add_argument("--format", choices=["summary", "json"], default="summary", help="输出格式")
    p_project_status.set_defaults(func=cmd_project_status)

    p_doctor = sub.add_parser("doctor", help="阶段感知的只读项目体检")
    p_doctor.add_argument("--chapter", type=int, default=None, help="目标章节号")
    p_doctor.add_argument("--deep", action="store_true", help="包含 dashboard 等较深检查")
    p_doctor.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    p_doctor.set_defaults(func=cmd_doctor)

    p_freeze = sub.add_parser("freeze", help="卷收尾冻结与 retcon 三选项裁决（T10）")
    p_freeze.add_argument("action", choices=["freeze", "retcon"])
    p_freeze.add_argument("--volume", type=int, required=True)
    p_freeze.add_argument("--force", action="store_true")
    p_freeze.add_argument("--choice", choices=["forward", "full", "revert"])
    p_freeze.add_argument("--reason", default="")
    p_freeze.add_argument("--affected", default="")
    p_freeze.add_argument("--format", choices=["text", "json"], default="text")
    p_freeze.set_defaults(func=cmd_freeze)

    p_timeline = sub.add_parser("timeline", help="卷纲时间线视图（build 导出 / sync 反向对账回写）")
    p_timeline.add_argument("action", choices=["build", "sync"])
    p_timeline.add_argument("--volume", type=int, required=True, help="卷号")
    p_timeline.add_argument("--apply", action="store_true", help="sync 时回写章纲卡")
    p_timeline.add_argument("--format", choices=["text", "json"], default="text")
    p_timeline.set_defaults(func=cmd_timeline)

    p_chapter_batch = sub.add_parser("chapter-batch", help="章纲批量（confirm 一次确认一批）")
    p_chapter_batch.add_argument("action", choices=["confirm"])
    p_chapter_batch.add_argument("--chapters", default="", help="逗号分隔章号")
    p_chapter_batch.add_argument("--format", choices=["text", "json"], default="text")
    p_chapter_batch.set_defaults(func=cmd_chapter_batch)

    p_regen = sub.add_parser("regen", help="regen 画廊（save/list/diff/adopt/discard）")
    p_regen.add_argument("action", choices=["save", "list", "diff", "adopt", "discard"])
    p_regen.add_argument("--domain", choices=["总纲", "章纲"], required=True)
    p_regen.add_argument("--key", default="")
    p_regen.add_argument("--version", type=int, default=None)
    p_regen.add_argument("--against", type=int, default=None)
    p_regen.add_argument("--content-file", default="")
    p_regen.add_argument("--force", action="store_true")
    p_regen.add_argument("--format", choices=["text", "json"], default="text")
    p_regen.set_defaults(func=cmd_regen)

    p_zones = sub.add_parser("zones", help="总纲三区结构（migrate 自动分区 / show 状态）")
    p_zones.add_argument("action", choices=["migrate", "show"])
    p_zones.add_argument("--dry-run", action="store_true")
    p_zones.add_argument("--format", choices=["text", "json"], default="text")
    p_zones.set_defaults(func=cmd_zones)

    p_impact = sub.add_parser("impact", help="影响反查：路径→受影响章/资产+三选项裁决建议（只读）")
    p_impact.add_argument("--path", required=True, help="书仓内相对路径")
    p_impact.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    p_impact.set_defaults(func=cmd_impact)

    p_author_sync = sub.add_parser("author-sync", help="作者修改留账：git diff→六域分类→journal+stale（0 token）")
    p_author_sync.add_argument("--confirm-migration", action="store_true", help="批量变更（>100 文件）确认记录为汇总事件")
    p_author_sync.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    p_author_sync.set_defaults(func=cmd_author_sync)

    p_domains = sub.add_parser("domains", help="书仓六域目录契约（init 建骨架 / check 体检）")
    p_domains.add_argument("action", choices=["init", "check"], help="init=幂等创建缺失骨架；check=只读契约检查")
    p_domains.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    p_domains.set_defaults(func=cmd_domains)

    p_materials = sub.add_parser("materials", help="素材工作台（T11 数据面 / T12 轨迹 / T13 入库画廊 / T14 卷审）")
    p_materials.add_argument(
        "action",
        choices=["list", "validate", "assemble", "seed", "log", "trajectory", "propose", "candidates", "adopt", "discard", "review", "apply-ruling"],
        help="子动作",
    )
    p_materials.add_argument("material_args", nargs=argparse.REMAINDER, help="子动作参数（--table/--k/--genre 等）")
    p_materials.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    p_materials.set_defaults(func=cmd_materials)

    p_style_domain = sub.add_parser("style-domain", help="文风域（migrate 宪法迁移 / fingerprint 指纹 / golden-* 金句库）")
    p_style_domain.add_argument("action", choices=["migrate", "fingerprint", "golden-add", "golden-list", "golden-feed"], help="子动作")
    p_style_domain.add_argument("--chapter", type=int, default=None, help="指纹单章口径 / 金句所在章")
    p_style_domain.add_argument("--text", default="", help="golden-add 金句摘录")
    p_style_domain.add_argument("--note", default="", help="golden-add 备注")
    p_style_domain.add_argument("--id", default="", help="golden-feed 金句编号")
    p_style_domain.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    p_style_domain.set_defaults(func=cmd_style_domain)

    p_learn = sub.add_parser("learn", help="学习闭环（F-12）：learn --from-journal 卷级归纳 / apply 确认回写 / show")
    p_learn.add_argument("action", choices=["learn", "apply", "show"], help="子动作")
    p_learn.add_argument("--from-journal", action="store_true", help="learn 数据源（journal）")
    p_learn.add_argument("--volume", type=int, default=None, help="卷级归纳口径")
    p_learn.add_argument("--suggestion", default="", help="apply 的建议文件")
    p_learn.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    p_learn.set_defaults(func=cmd_learn)

    p_power = sub.add_parser("power", help="战力域（T18/T19，F-09）：extract/validate 锚点、battle/inflate 账本、check 校验")
    p_power.add_argument("action", choices=["extract", "validate", "battle", "inflate", "check"], help="子动作")
    p_power.add_argument("power_args", nargs=argparse.REMAINDER, help="子动作参数（--chapter/--matchup/--apply 等）")
    p_power.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    p_power.set_defaults(func=cmd_power)

    p_forge = sub.add_parser("forge", help="设定工坊（T20，F-08，提案模式）：prepare/save/adopt/confirm/list")
    p_forge.add_argument("action", choices=["prepare", "save", "adopt", "confirm", "list"], help="子动作")
    p_forge.add_argument("--category", default="", help="境界/功法/法宝/命名")
    p_forge.add_argument("--file", default="", help="save：提案 md 文件")
    p_forge.add_argument("--version", type=int, default=None, help="adopt：画廊版本")
    p_forge.add_argument("--proposal", type=int, default=None, help="adopt：提案编号（1-5）")
    p_forge.add_argument("--draft", default="", help="confirm：草案文件")
    p_forge.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    p_forge.set_defaults(func=cmd_forge)

    p_timeline_check = sub.add_parser("timeline-check", help="程序化校验卷时间线（单调递增/倒计时算术）")
    p_timeline_check.add_argument("--volume", type=int, required=True, help="卷号")
    p_timeline_check.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    p_timeline_check.set_defaults(func=cmd_timeline_check)

    p_meter = sub.add_parser("meter", help="章级 token 计量（读 ZCode 用量库，含子代理）")
    meter_sub = p_meter.add_subparsers(dest="meter_action", required=True)
    p_meter_start = meter_sub.add_parser("start", help="写章起点：建计量标记")
    p_meter_start.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_meter_start.add_argument("--session", default="", help="显式主会话 id（缺省从用量库推断最近完成的非子代理轮）")
    p_meter_start.add_argument("--db", default="", help="用量库路径（缺省 ~/.zcode/cli/db/db.sqlite）")
    p_meter_stop = meter_sub.add_parser("stop", help="聚合关账：一行结论 + 结果文件 + 移除标记")
    p_meter_stop.add_argument("--db", default="")
    p_meter_report = meter_sub.add_parser("report", help="只读聚合（不移除标记）")
    p_meter_report.add_argument("--db", default="")
    p_meter.set_defaults(func=cmd_meter)

    p_setting_read = sub.add_parser("setting-read", help="读取设定文件原文（L2，按需展开）")
    p_setting_read.add_argument("--name", required=True, help="设定名（如 世界观/力量体系/主角卡）")
    p_setting_read.add_argument("--max-chars", type=int, default=0, help="最多输出字符（0=全文）")
    p_setting_read.set_defaults(func=cmd_setting_read)

    p_write_gate = sub.add_parser("write-gate", help="写章自然边界校验")
    p_write_gate.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_write_gate.add_argument("--stage", choices=["prewrite", "precommit", "postcommit"], required=True, help="校验阶段")
    p_write_gate.add_argument(
        "--format",
        choices=["compact", "json", "text"],
        default="compact",
        help="输出格式（compact=一行结论默认；json=全量 JSON；快照恒落盘 .webnovel/tmp/last_gate_<stage>.json）",
    )
    p_write_gate.set_defaults(func=cmd_write_gate)

    p_projections = sub.add_parser("projections", help="从已有 commit 补跑或重放 projection")
    projections_sub = p_projections.add_subparsers(dest="projection_action", required=True)
    p_projection_retry = projections_sub.add_parser("retry", help="补跑单章 projection")
    p_projection_retry.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_projection_retry.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_projection_retry.set_defaults(func=cmd_projections)
    p_projection_replay = projections_sub.add_parser("replay", help="按章节范围重放 projection")
    p_projection_replay.add_argument("--from-chapter", type=int, required=True, help="起始章节号")
    p_projection_replay.add_argument("--to-chapter", type=int, required=True, help="结束章节号")
    p_projection_replay.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_projection_replay.set_defaults(func=cmd_projections)

    p_user_report = sub.add_parser("user-report", help="渲染作者友好的最终报告")
    p_user_report.add_argument("--stage", choices=["init", "plan", "write", "review"], required=True, help="报告阶段")
    p_user_report.add_argument("--chapter", type=int, default=None, help="目标章节号")
    p_user_report.add_argument("--volume", type=int, default=None, help="目标卷号")
    p_user_report.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    p_user_report.set_defaults(func=cmd_user_report)

    p_run_ledger = sub.add_parser("run-ledger", help="记录或查询写章断点续跑状态")
    run_ledger_sub = p_run_ledger.add_subparsers(dest="ledger_action", required=True)
    p_record_write_step = run_ledger_sub.add_parser("record-write-step", help="记录写章步骤状态")
    p_record_write_step.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_record_write_step.add_argument("--step", choices=["draft", "review", "data", "commit", "projection", "backup"], required=True)
    p_record_write_step.add_argument("--status", required=True)
    p_record_write_step.add_argument("--mode", default="default")
    p_record_write_step.add_argument("--inputs-json", default="{}")
    p_record_write_step.add_argument("--outputs-json", default="{}")
    p_record_write_step.add_argument("--problems-json", default="[]")
    p_record_write_step.add_argument("--auto-handled-json", default="[]")
    p_record_write_step.add_argument("--duration-ms", type=int, default=0)
    p_record_write_step.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_record_write_step.set_defaults(func=cmd_run_ledger)
    p_record_write_steps = run_ledger_sub.add_parser(
        "record-write-steps", help="批量记录写章步骤（S9/D2：一条命令冲账多步）"
    )
    p_record_write_steps.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_record_write_steps.add_argument("--steps-json", required=True, help='步骤数组 JSON：[{"step":"draft","status":"completed"},...]')
    p_record_write_steps.add_argument("--mode", default="default")
    p_record_write_steps.set_defaults(func=cmd_run_ledger)
    p_record_subagent = run_ledger_sub.add_parser("record-subagent", help="记录子代理运行结果")
    p_record_subagent.add_argument("--run-id", required=True)
    p_record_subagent.add_argument("--name", required=True)
    p_record_subagent.add_argument("--user-label", default="")
    p_record_subagent.add_argument("--status", choices=["completed", "partial", "failed", "skipped"], required=True)
    p_record_subagent.add_argument("--command", default="")
    p_record_subagent.add_argument("--stage", default="")
    p_record_subagent.add_argument("--chapter", type=int, default=None)
    p_record_subagent.add_argument("--volume", type=int, default=None)
    p_record_subagent.add_argument("--problems-json", default="[]")
    p_record_subagent.add_argument("--auto-handled-json", default="[]")
    p_record_subagent.add_argument("--needs-user-action", action="store_true")
    p_record_subagent.add_argument("--duration-ms", type=int, default=0)
    p_record_subagent.add_argument("--outputs-json", default="[]")
    p_record_subagent.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_record_subagent.set_defaults(func=cmd_run_ledger)
    p_get_subagent = run_ledger_sub.add_parser("get-subagent-runs", help="读取子代理运行结果")
    p_get_subagent.add_argument("--command", default="")
    p_get_subagent.add_argument("--stage", default="")
    p_get_subagent.add_argument("--chapter", type=int, default=None)
    p_get_subagent.add_argument("--latest-only", action="store_true")
    p_get_subagent.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_get_subagent.set_defaults(func=cmd_run_ledger)
    p_write_resume = run_ledger_sub.add_parser("write-resume", help="输出写章断点续跑建议")
    p_write_resume.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_write_resume.add_argument("--mode", default="default", help="写章模式")
    p_write_resume.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_write_resume.set_defaults(func=cmd_run_ledger)

    p_run_log = sub.add_parser("run-log", help="写入脱敏运行日志")
    p_run_log.add_argument("--event", required=True, help="事件名")
    p_run_log.add_argument("--payload-json", default="{}", help="要写入日志的 JSON 对象")
    p_run_log.add_argument("--append", action="store_true", help="追加而不是覆盖 run_last.log")
    p_run_log.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    p_run_log.set_defaults(func=cmd_run_log)

    p_use = sub.add_parser("use", help="绑定当前工作区使用的书项目（写入指针/registry）")
    p_use.add_argument("project_root", help="书项目根目录（必须包含 .webnovel/state.json）")
    p_use.add_argument("--workspace-root", help="工作区根目录（可选；默认由运行环境推断）")
    p_use.set_defaults(func=cmd_use)

    # Pass-through to data modules
    p_index = sub.add_parser("index", help="转发到 index_manager")
    p_index.add_argument("args", nargs=argparse.REMAINDER)

    p_state = sub.add_parser("state", help="转发到 state_manager")
    p_state.add_argument("args", nargs=argparse.REMAINDER)

    p_rag = sub.add_parser("rag", help="转发到 rag_adapter")
    p_rag.add_argument("args", nargs=argparse.REMAINDER)

    p_style = sub.add_parser("style", help="转发到 style_sampler")
    p_style.add_argument("args", nargs=argparse.REMAINDER)

    p_entity = sub.add_parser("entity", help="转发到 entity_linker")
    p_entity.add_argument("args", nargs=argparse.REMAINDER)

    p_context = sub.add_parser("context", help="转发到 context_manager")
    p_context.add_argument("args", nargs=argparse.REMAINDER)

    p_memory = sub.add_parser("memory", help="转发到 memory.store")
    p_memory.add_argument("args", nargs=argparse.REMAINDER)

    p_migrate = sub.add_parser("migrate", help="转发到 migrate_state_to_sqlite")
    p_migrate.add_argument("args", nargs=argparse.REMAINDER)

    # Pass-through to scripts
    p_status = sub.add_parser("status", help="转发到 status_reporter.py")
    p_status.add_argument("args", nargs=argparse.REMAINDER)

    p_update_state = sub.add_parser("update-state", help="转发到 update_state.py")
    p_update_state.add_argument("args", nargs=argparse.REMAINDER)

    p_backup = sub.add_parser("backup", help="转发到 backup_manager.py")
    p_backup.add_argument("args", nargs=argparse.REMAINDER)

    p_archive = sub.add_parser("archive", help="转发到 archive_manager.py")
    p_archive.add_argument("args", nargs=argparse.REMAINDER)

    p_init = sub.add_parser("init", help="转发到 init_project.py（初始化项目）")
    p_init.add_argument("args", nargs=argparse.REMAINDER)

    p_extract_context = sub.add_parser("extract-context", help="转发到 extract_chapter_context.py")
    p_extract_context.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_extract_context.add_argument("--format", choices=["json"], default="json",
                                   help="输出格式（始终 JSON，text 渲染由 context-agent 负责）")

    p_story_system = sub.add_parser("story-system", help="转发到 story_system.py")
    p_story_system.add_argument("args", nargs=argparse.REMAINDER)

    p_story_events = sub.add_parser("story-events", help="转发到 story_events.py")
    p_story_events.add_argument("--chapter", type=int, default=0, help="目标章节号")
    p_story_events.add_argument("--limit", type=int, default=200, help="查询条数")
    p_story_events.add_argument("--health", action="store_true", help="输出事件链健康信息")

    p_commit = sub.add_parser("chapter-commit", help="转发到 chapter_commit.py")
    p_commit.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_commit.add_argument("--review-result", required=True, help="review_result JSON 文件")
    p_commit.add_argument("--fulfillment-result", required=True, help="fulfillment_result JSON 文件")
    p_commit.add_argument("--disambiguation-result", required=True, help="disambiguation_result JSON 文件")
    p_commit.add_argument("--extraction-result", required=True, help="extraction_result JSON 文件")

    p_memory_contract = sub.add_parser("memory-contract", help="转发到 memory_cli.py")
    p_memory_contract.add_argument("args", nargs=argparse.REMAINDER)

    p_project_memory = sub.add_parser("project-memory", help="转发到 project_memory.py")
    p_project_memory.add_argument("args", nargs=argparse.REMAINDER)

    p_review_pipeline = sub.add_parser("review-pipeline", help="转发到 review_pipeline.py")
    p_review_pipeline.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_review_pipeline.add_argument("--review-results", required=True, help="reviewer 原始结果 JSON 文件")
    p_review_pipeline.add_argument("--metrics-out", default="", help="metrics 输出文件")
    p_review_pipeline.add_argument("--report-file", default="", help="审查报告路径")
    p_review_pipeline.add_argument("--save-metrics", action="store_true", help="直接写入 index.db")

    p_placeholder_scan = sub.add_parser("placeholder-scan", help="扫描大纲/设定集未补齐占位")
    p_placeholder_scan.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")

    p_master_outline_sync = sub.add_parser("master-outline-sync", help="当前卷规划完成后写回 V+1 最小总纲锚点")
    p_master_outline_sync.add_argument("--volume", type=int, required=True, help="当前已完成规划的卷号")
    p_master_outline_sync.add_argument("--writeback-file", default="", help="显式结构化写回 JSON")
    p_master_outline_sync.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")

    knowledge_parser = sub.add_parser("knowledge", help="时序知识查询")
    knowledge_sub = knowledge_parser.add_subparsers(dest="knowledge_action")

    qs_parser = knowledge_sub.add_parser("query-entity-state", help="查询实体在指定章节的状态")
    qs_parser.add_argument("--entity", required=True, help="实体 ID")
    qs_parser.add_argument("--at-chapter", type=int, required=True, help="目标章节号")

    qr_parser = knowledge_sub.add_parser("query-relationships", help="查询实体在指定章节的关系")
    qr_parser.add_argument("--entity", required=True, help="实体 ID")
    qr_parser.add_argument("--at-chapter", type=int, required=True, help="目标章节号")

    kb_parser = knowledge_sub.add_parser("boundary", help="知识边界（A1/T21）：信息差按章输出知晓状态")
    kb_parser.add_argument("--chapter", type=int, required=True, dest="boundary_chapter", help="目标章节号")
    kb_parser.add_argument("--entity", default="", dest="boundary_entity", help="限定实体（可选）")
    kb_parser.add_argument("--format", choices=["json", "text"], default="json", dest="boundary_format", help="输出格式")

    # 兼容：允许 `--project-root` 出现在任意位置（减少 agents/skills 拼命令的出错率）
    from .cli_args import normalize_global_project_root

    argv = normalize_global_project_root(sys.argv[1:])
    args, unknown_args = parser.parse_known_args(argv)
    _LAST_ARGS = args

    # where/use 直接执行
    if hasattr(args, "func"):
        if unknown_args:
            parser.error(f"unrecognized arguments: {' '.join(unknown_args)}")
        code = int(args.func(args) or 0)
        raise SystemExit(code)

    tool = args.tool
    if unknown_args and tool not in PASSTHROUGH_TOOLS:
        parser.error(f"unrecognized arguments: {' '.join(unknown_args)}")

    rest = _passthrough_tail(argv, tool) if tool in PASSTHROUGH_TOOLS else list(getattr(args, "args", []) or [])
    # argparse.REMAINDER 可能以 `--` 开头占位，这里去掉
    if rest[:1] == ["--"]:
        rest = rest[1:]
    rest = _strip_project_root_args(rest)

    # init 是创建项目，不应该依赖/注入已存在 project_root
    if tool == "init":
        raise SystemExit(_run_script("init_project.py", rest))

    # knowledge boundary（M4/T21，A1）：信息差表为纯 md，不依赖 index.db——宽松解析支持纯 v7 书仓
    if tool == "knowledge" and getattr(args, "knowledge_action", "") == "boundary":
        from .info_gap import boundary as knowledge_boundary
        from .cli_output import print_success

        boundary_root = _resolve_root_lenient(args.project_root)
        boundary_report = knowledge_boundary(
            boundary_root, chapter=args.boundary_chapter, entity=args.boundary_entity or None
        )
        if getattr(args, "boundary_format", "json") == "json":
            print_success(boundary_report, message="knowledge_boundary")
        else:
            for fact in boundary_report["facts"]:
                state = "已知" if fact["该章已知"] else "未知"
                taboo = f"｜禁忌 {fact['泄露禁忌']}" if fact["泄露禁忌"] else ""
                print(f"[{state}] {fact['信息点']}（知晓者 {'、'.join(fact['知晓者'])}，自第 {fact['知晓章']} 章）{taboo}")
        raise SystemExit(0)

    # 其余工具：统一解析 project_root 后前置给下游
    project_root = _resolve_root(args.project_root)
    forward_args = ["--project-root", str(project_root)]

    if tool == "index":
        raise SystemExit(_run_data_module("index_manager", [*forward_args, *rest]))
    if tool == "state":
        raise SystemExit(_run_data_module("state_manager", [*forward_args, *rest]))
    if tool == "rag":
        raise SystemExit(_run_data_module("rag_adapter", [*forward_args, *rest]))
    if tool == "style":
        raise SystemExit(_run_data_module("style_sampler", [*forward_args, *rest]))
    if tool == "entity":
        raise SystemExit(_run_data_module("entity_linker", [*forward_args, *rest]))
    if tool == "context":
        raise SystemExit(_run_data_module("context_manager", [*forward_args, *rest]))
    if tool == "memory":
        raise SystemExit(_run_data_module("memory.store", [*forward_args, *rest]))
    if tool == "migrate":
        raise SystemExit(_run_data_module("migrate_state_to_sqlite", [*forward_args, *rest]))

    if tool == "status":
        raise SystemExit(_run_script("status_reporter.py", [*forward_args, *rest]))
    if tool == "update-state":
        raise SystemExit(_run_script("update_state.py", [*forward_args, *rest]))
    if tool == "backup":
        raise SystemExit(_run_script("backup_manager.py", [*forward_args, *rest]))
    if tool == "archive":
        raise SystemExit(_run_script("archive_manager.py", [*forward_args, *rest]))
    if tool == "extract-context":
        return_args = [*forward_args, "--chapter", str(args.chapter), "--format", str(args.format)]
        raise SystemExit(_run_script("extract_chapter_context.py", return_args))
    if tool == "story-system":
        raise SystemExit(_run_script("story_system.py", [*forward_args, *rest]))
    if tool == "story-events":
        return_args = [*forward_args, "--limit", str(args.limit)]
        if args.chapter:
            return_args.extend(["--chapter", str(args.chapter)])
        if args.health:
            return_args.append("--health")
        raise SystemExit(_run_script("story_events.py", return_args))
    if tool == "chapter-commit":
        return_args = [*forward_args, "--chapter", str(args.chapter)]
        if args.review_result:
            return_args.extend(["--review-result", str(args.review_result)])
        if args.fulfillment_result:
            return_args.extend(["--fulfillment-result", str(args.fulfillment_result)])
        if args.disambiguation_result:
            return_args.extend(["--disambiguation-result", str(args.disambiguation_result)])
        if args.extraction_result:
            return_args.extend(["--extraction-result", str(args.extraction_result)])
        raise SystemExit(_run_script("chapter_commit.py", return_args))
    if tool == "memory-contract":
        raise SystemExit(_run_script("memory_cli.py", [*forward_args, *rest]))
    if tool == "project-memory":
        raise SystemExit(_run_script("project_memory.py", [*forward_args, *rest]))
    if tool == "review-pipeline":
        return_args = [
            *forward_args,
            "--chapter", str(args.chapter),
            "--review-results", str(args.review_results),
        ]
        if args.metrics_out:
            return_args.extend(["--metrics-out", str(args.metrics_out)])
        if args.report_file:
            return_args.extend(["--report-file", str(args.report_file)])
        if args.save_metrics:
            return_args.append("--save-metrics")
        raise SystemExit(_run_script("review_pipeline.py", return_args))
    if tool == "placeholder-scan":
        raise SystemExit(_run_data_module("placeholder_scanner", [*forward_args, "--format", str(args.format)]))
    if tool == "master-outline-sync":
        return_args = [*forward_args, "--volume", str(args.volume), "--format", str(args.format)]
        if args.writeback_file:
            return_args.extend(["--writeback-file", str(args.writeback_file)])
        raise SystemExit(_run_script("update_master_outline.py", return_args))

    if tool == "knowledge":
        from .knowledge_query import KnowledgeQuery
        from .cli_output import print_success
        kq = KnowledgeQuery(project_root)
        if args.knowledge_action == "query-entity-state":
            result = kq.entity_state_at_chapter(args.entity, args.at_chapter)
            print_success(result, message="entity_state_at_chapter")
            raise SystemExit(0)
        elif args.knowledge_action == "query-relationships":
            result = kq.entity_relationships_at_chapter(args.entity, args.at_chapter)
            print_success(result, message="entity_relationships_at_chapter")
            raise SystemExit(0)

    raise SystemExit(2)


if __name__ == "__main__":
    main()
