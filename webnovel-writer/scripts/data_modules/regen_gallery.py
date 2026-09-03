"""regen 画廊（webnovel-copilot-300 · M1/T7，流程 F-02/F-04）。

gallery = 生成物的版本仓库；采纳（adopt）才写回目标文件。
- 总纲：`大纲/regen/总纲/v{N}.md`，采纳写回 `大纲/总纲.md`
- 章纲：`大纲/regen/章纲/{key}/v{N}.md`，采纳写回 `大纲/章纲/{key}.md`
- current 指针（D7）：画廊目录内 `current` 单行文件（被采纳的版本号）
- 上限（D3）：默认 3 版；超限需 force。
红线：画廊只增不改；采纳/丢弃留 journal（author_journal append-only）。
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

from .author_journal import append_events

GALLERY_SCHEMA_VERSION = "regen/1"
MAX_VERSIONS = 3

_MASTER_TARGET = Path("大纲") / "总纲.md"
_CHAPTER_TARGET_DIR = Path("大纲") / "章纲"


def _gallery_dir(project_root: str | Path, domain: str, key: str) -> Path:
    root = Path(project_root)
    if domain == "总纲":
        return root / "大纲" / "regen" / "总纲"
    if domain == "章纲":
        return root / "大纲" / "regen" / "章纲" / key
    raise ValueError(f"unsupported domain: {domain}")


def _target_path(project_root: str | Path, domain: str, key: str) -> Path:
    root = Path(project_root)
    if domain == "总纲":
        return root / _MASTER_TARGET
    if domain == "章纲":
        return root / _CHAPTER_TARGET_DIR / f"{key}.md"
    raise ValueError(f"unsupported domain: {domain}")


def _journal(project_root: str | Path, action: str, domain: str, key: str, extra: dict[str, Any] | None = None) -> None:
    event: dict[str, Any] = {
        "actor": "author",
        "action": action,
        "domain": domain,
        "path": str(_target_path(project_root, domain, key).relative_to(Path(project_root))),
        "change_kind": "structure",
        "diff_stat": {"ins": 0, "del": 0},
        "summary": "",
        "impact": [],
    }
    if extra:
        event.update(extra)
    append_events(project_root, [event])


def list_versions(project_root: str | Path, *, domain: str, key: str) -> list[dict[str, Any]]:
    gallery = _gallery_dir(project_root, domain, key)
    if not gallery.is_dir():
        return []
    versions: list[dict[str, Any]] = []
    for file in gallery.glob("v*.md"):
        match = re.fullmatch(r"v(\d+)", file.stem)
        if match:
            versions.append({"version": int(match.group(1)), "path": str(file), "size": file.stat().st_size})
    return sorted(versions, key=lambda v: v["version"])


def save_version(project_root: str | Path, *, domain: str, key: str, content: str, force: bool = False) -> dict[str, Any]:
    versions = list_versions(project_root, domain=domain, key=key)
    next_version = (versions[-1]["version"] + 1) if versions else 1
    if next_version > MAX_VERSIONS and not force:
        return {"ok": False, "error": "max_versions", "max": MAX_VERSIONS, "count": len(versions)}
    gallery = _gallery_dir(project_root, domain, key)
    gallery.mkdir(parents=True, exist_ok=True)
    path = gallery / f"v{next_version}.md"
    path.write_text(content, encoding="utf-8", newline="\n")
    _journal(project_root, "regen", domain, key, {"diff_stat": {"ins": len(content.splitlines())}})
    return {"ok": True, "version": next_version, "path": str(path), "schema_version": GALLERY_SCHEMA_VERSION}


def read_current(project_root: str | Path, *, domain: str, key: str) -> int | None:
    pointer = _gallery_dir(project_root, domain, key) / "current"
    if not pointer.is_file():
        return None
    try:
        return int(pointer.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _version_path(project_root: str | Path, domain: str, key: str, version: int) -> Path:
    return _gallery_dir(project_root, domain, key) / f"v{version}.md"


def diff_versions(project_root: str | Path, *, domain: str, key: str, a: int, b: int) -> str:
    pa, pb = _version_path(project_root, domain, key, a), _version_path(project_root, domain, key, b)
    if not pa.is_file() or not pb.is_file():
        return ""
    lines_a = pa.read_text(encoding="utf-8").splitlines()
    lines_b = pb.read_text(encoding="utf-8").splitlines()
    diff = difflib.unified_diff(lines_a, lines_b, fromfile=f"v{a}", tofile=f"v{b}", lineterm="")
    return "\n".join(diff)


def adopt_version(project_root: str | Path, *, domain: str, key: str, version: int) -> dict[str, Any]:
    source = _version_path(project_root, domain, key, version)
    if not source.is_file():
        return {"ok": False, "error": "version_missing"}
    content = source.read_text(encoding="utf-8")
    target = _target_path(project_root, domain, key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    pointer = _gallery_dir(project_root, domain, key) / "current"
    pointer.write_text(f"{version}\n", encoding="utf-8", newline="\n")
    _journal(project_root, "adopt", domain, key, {"summary": f"adopt v{version}"})
    return {"ok": True, "version": version, "target": str(target)}


def discard_version(project_root: str | Path, *, domain: str, key: str, version: int) -> dict[str, Any]:
    source = _version_path(project_root, domain, key, version)
    if not source.is_file():
        return {"ok": False, "error": "version_missing"}
    source.unlink()
    _journal(project_root, "discard", domain, key, {"summary": f"discard v{version}"})
    return {"ok": True, "version": version}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="regen 画廊（T7）")
    parser.add_argument("action", choices=["save", "list", "diff", "adopt", "discard"])
    parser.add_argument("--domain", choices=["总纲", "章纲"], required=True)
    parser.add_argument("--key", default="", help="章纲号（章纲域必填）")
    parser.add_argument("--version", type=int, default=None)
    parser.add_argument("--against", type=int, default=None, help="diff 的另一版本")
    parser.add_argument("--content-file", default="", help="save 时读取内容文件")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    root = Path(args.project_root)
    if args.action == "save":
        content = Path(args.content_file).read_text(encoding="utf-8") if args.content_file else ""
        report = save_version(root, domain=args.domain, key=args.key, content=content, force=args.force)
    elif args.action == "list":
        report = {"ok": True, "versions": list_versions(root, domain=args.domain, key=args.key)}
    elif args.action == "diff":
        report = {"ok": True, "diff": diff_versions(root, domain=args.domain, key=args.key, a=args.version or 0, b=args.against or 0)}
    elif args.action == "adopt":
        report = adopt_version(root, domain=args.domain, key=args.key, version=args.version or 0)
    elif args.action == "discard":
        report = discard_version(root, domain=args.domain, key=args.key, version=args.version or 0)
    else:
        report = {"ok": False, "error": "unknown"}

    if args.format == "json":
        print(_json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if args.action == "list":
            for v in report["versions"]:
                print(f"v{v['version']}  {v['size']}B  {v['path']}")
            print(f"current: {read_current(root, domain=args.domain, key=args.key)}")
        elif args.action == "diff":
            print(report["diff"] or "(无差异或版本缺失)")
        else:
            print("OK" if report.get("ok") else f"ERROR {report.get('error')}")
    return 0 if report.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
