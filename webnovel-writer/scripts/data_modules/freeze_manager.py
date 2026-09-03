"""freeze / retcon（webnovel-copilot-300 · M1/T10，流程 F-10/F-07）。

- freeze：卷收尾把 素材/活/ 快照到 素材/定版/v{NN}/（含 manifest.json，源文件 sha1）；
  前置检查（settled 完整性/stale 积压）以 warnings 透出（作者显式发起，v1 不硬阻断）；
  重复冻结拒绝（force 可覆盖）；留 journal(freeze) 与 `演化/freeze-v{NN}.json` 记录。
- retcon：记录三选项裁决（forward/full/revert）+ 受影响章，留 journal(retcon)
  与 `演化/retcon-v{NN}-{ts}.json`。实际逐章修改由会话内作者/AI 执行（P1：作者确认后动卡）。
红线：快照为复制，绝不改动活层；不做自动 git commit（作者事务自行收口）。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .author_journal import append_events, unconsumed_stale

FREEZE_SCHEMA_VERSION = "freeze/1"
RETCON_CHOICES: tuple[str, ...] = ("forward", "full", "revert")
RETCON_LABELS: dict[str, str] = {
    "forward": "① 只改今后：定版不动，新章按新规则并记录例外",
    "full": "② 全书 retcon：按影响清单逐章修改，留 retcon(N) 事务",
    "revert": "③ 还原：放弃本次修改，保持既有定版",
}

_LIVE_DIR = Path("素材") / "活"
_DEFINITIVE_DIR = Path("素材") / "定版"
_POWER_ANCHOR_REL = Path("设定") / "力量锚点.yaml"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha1_of(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_files(live_dir: Path) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    if live_dir.is_dir():
        for file in sorted(live_dir.iterdir()):
            if file.is_file():
                files.append({"path": file.name, "sha1": _sha1_of(file)})
    return files


def freeze_volume(project_root: str | Path, *, volume: int, force: bool = False) -> dict[str, Any]:
    root = Path(project_root)
    live_dir = root / _LIVE_DIR
    target = root / _DEFINITIVE_DIR / f"v{int(volume):02d}"

    if target.is_dir() and not force:
        return {"ok": False, "error": "already_frozen", "volume": volume, "target": str(target)}

    warnings: list[str] = []
    live_files = _manifest_files(live_dir)
    if not any(f["path"] != "README.md" for f in live_files):
        warnings.append("素材/活/ 无实质条目（仅 README），冻结为空快照")
    stale = unconsumed_stale(root)
    if stale:
        warnings.append(f"stale 未消费 {len(stale)} 项（冻结前建议消化）")

    # 快照（复制，不改活层）
    if target.is_dir():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    for file in live_files:
        source = live_dir / file["path"]
        if source.is_file():
            shutil.copy2(source, target / file["path"])

    manifest: dict[str, Any] = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "volume": int(volume),
        "frozen_at": _utc_now_iso(),
        "source_files": live_files,
    }
    anchor = root / _POWER_ANCHOR_REL
    if anchor.is_file():
        manifest["power_anchor_sha1"] = _sha1_of(anchor)
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    # journal + 演化记录
    append_events(
        root,
        [
            {
                "actor": "author",
                "action": "freeze",
                "domain": "素材",
                "path": str(target.relative_to(root)),
                "change_kind": "structure",
                "diff_stat": {"ins": len(live_files)},
                "summary": f"卷 {volume} 素材定版冻结（{len(live_files)} 个文件）",
                "impact": [],
            }
        ],
    )
    evolution_dir = root / "演化"
    evolution_dir.mkdir(parents=True, exist_ok=True)
    (evolution_dir / f"freeze-v{int(volume):02d}.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )

    # M6/T30（A7）：冻结后产出卷纲-实际对账报告（失败不阻断冻结事务）
    reconcile_hint = ""
    try:
        from .volume_reconcile import reconcile_volume

        reconcile_report = reconcile_volume(root, volume=int(volume))
        if reconcile_report.get("ok"):
            reconcile_hint = reconcile_report["report_path"]
            warnings.append(f"卷纲-实际对账已产出：{reconcile_hint}")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"卷纲-实际对账失败：{exc}")

    return {
        "ok": True,
        "schema_version": FREEZE_SCHEMA_VERSION,
        "volume": int(volume),
        "target": str(target),
        "files": len(live_files),
        "warnings": warnings,
        "reconcile_report": reconcile_hint,
    }


def record_retcon(
    project_root: str | Path,
    *,
    volume: int,
    choice: str,
    reason: str = "",
    affected_chapters: list[int] | None = None,
) -> dict[str, Any]:
    root = Path(project_root)
    if choice not in RETCON_CHOICES:
        return {"ok": False, "error": "invalid_choice", "allowed": list(RETCON_CHOICES)}

    chapters = sorted(int(c) for c in (affected_chapters or []))
    summary = f"卷 {volume} retcon 裁决：{RETCON_LABELS[choice]}（{reason}）"
    append_events(
        root,
        [
            {
                "actor": "author",
                "action": "retcon",
                "domain": "设定",
                "path": f"素材/定版/v{int(volume):02d}",
                "change_kind": "structure",
                "diff_stat": {"ins": 0, "del": 0},
                "summary": summary,
                "impact": [f"affected_chapters:{','.join(map(str, chapters))}"] if chapters else [],
            }
        ],
    )
    record = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "volume": int(volume),
        "choice": choice,
        "reason": reason,
        "affected_chapters": chapters,
        "recorded_at": _utc_now_iso(),
    }
    evolution_dir = root / "演化"
    evolution_dir.mkdir(parents=True, exist_ok=True)
    (evolution_dir / f"retcon-v{int(volume):02d}-{_utc_now_iso().replace(':', '')}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    return {"ok": True, "schema_version": FREEZE_SCHEMA_VERSION, **record}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="卷收尾冻结与 retcon 裁决（T10）")
    parser.add_argument("action", choices=["freeze", "retcon"])
    parser.add_argument("--volume", type=int, required=True)
    parser.add_argument("--force", action="store_true", help="freeze 覆盖既有定版")
    parser.add_argument("--choice", choices=list(RETCON_CHOICES), help="retcon 三选项")
    parser.add_argument("--reason", default="")
    parser.add_argument("--affected", default="", help="逗号分隔受影响章号")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    if args.action == "freeze":
        report = freeze_volume(root, volume=args.volume, force=args.force)
    else:
        chapters = [int(c) for c in args.affected.split(",") if c.strip()]
        report = record_retcon(
            root, volume=args.volume, choice=args.choice or "forward", reason=args.reason, affected_chapters=chapters
        )

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if not report.get("ok"):
            print(f"ERROR {report.get('error')}")
        elif args.action == "freeze":
            print(f"OK freeze v{report['volume']:02d}: {report['files']} 文件 → {report['target']}")
            for warning in report.get("warnings") or []:
                print(f"  WARN {warning}")
        else:
            print(f"OK retcon 卷{report['volume']}: {RETCON_LABELS[report['choice']]}")
            if report.get("affected_chapters"):
                print(f"  受影响章：{report['affected_chapters']}")
    return 0 if report.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
