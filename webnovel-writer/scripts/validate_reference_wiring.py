#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_reference_writing / 引用对账（webnovel-copilot-300 · M5/T27，R15/F-19）。

三方对账：references/ 与 templates/ 下的 md 资产 ↔ reference-loading-map 登记 ↔
skills/agents 实际引用。漂移三类：
- orphan：文件存在、无任何消费者引用、loading-map 也未登记（含退役登记）；
- unwired：loading-map 登记为直接加载，但没有任何 skill/agent 引用它；
- missing：被引用或被登记，但文件不存在。

退出码：有漂移 = 1（发版链硬门禁）；0 = 清零。
用法：python -X utf8 validate_reference_wiring.py [--root 插件根] [--format text|json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SCHEMA = "reference-wiring-report/v1"
_AUDIT_DIRS = ("references/index",)  # 自审文档本身不作为资产对账
_EXCLUDED_FILES = {"README.md"}
# 代码/数据驱动消费目录：init_project.py、genre 解析、CSV_CONFIG、reference_search、
# 素材播种等按目录整批消费——文本引用扫描覆盖不到，豁免 orphan 判定（missing 仍报）。
CODE_CONSUMED_DIRS: tuple[str, ...] = ("templates/genres", "templates/output", "references/csv")
_PATH_TOKEN = re.compile(r"[\w\-／/]*(?:references|templates)/[\w\-./]+\.md")
_MD_GLOB = "**/*.md"


def _plugin_root(root: Path | None) -> Path:
    if root is not None:
        return root
    here = Path(__file__).resolve().parent.parent
    return here if (here / ".zcode-plugin").is_dir() else here / "webnovel-writer"


def _collect_assets(root: Path) -> set[str]:
    assets: set[str] = set()
    for base in ("references", "templates"):
        for path in (root / base).rglob("*.md"):
            rel = path.relative_to(root).as_posix()
            if any(rel.startswith(a) for a in _AUDIT_DIRS):
                continue
            if path.name in _EXCLUDED_FILES:
                continue
            assets.add(rel)
    return assets


def _collect_consumers(root: Path) -> dict[str, list[str]]:
    """消费者文件 → 其文本（skills + agents）。"""
    consumers: dict[str, list[str]] = {}
    for base in ("skills", "agents"):
        for path in sorted((root / base).rglob("*.md")):
            consumers[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
    return consumers


def _referenced_paths(text: str) -> set[str]:
    found: set[str] = set()
    for token in _PATH_TOKEN.findall(text):
        token = token.replace("／", "/").lstrip("./")
        # \w 会吞 CJK 前缀（如「读references/x.md」）——截到最后一个合法目录起点
        for anchor in ("references/", "templates/"):
            index = token.rfind(anchor)
            if index > 0:
                token = token[index:]
                break
        found.add(token)
    return found


def _referenced_assets(root: Path, consumers: dict[str, list[str]]) -> tuple[dict[str, list[str]], set[str]]:
    """把消费者文本里的路径 token 解析为真实资产路径。

    解析顺序：插件根相对 → 消费者文件所在目录相对 → 其上级（skill 根）。
    返回 (资产路径 → 消费者列表, 解析失败的裸 token 集合)。
    """
    resolved: dict[str, list[str]] = {}
    unresolved: set[str] = set()
    consumer_dirs = sorted({Path(c).parent for c in consumers})
    for consumer, text in consumers.items():
        for token in _referenced_paths(text):
            candidates = [root / token]
            candidates += [root / d / token for d in consumer_dirs]
            hit = next((c for c in candidates if c.is_file()), None)
            if hit is not None:
                asset = hit.relative_to(root).as_posix()
                if consumer not in resolved.setdefault(asset, []):
                    resolved[asset].append(consumer)
            else:
                unresolved.add(token)
    return resolved, unresolved


def _load_map_entries(root: Path) -> tuple[set[str], set[str]]:
    """loading-map 解析：(登记路径集合, 显式退役路径集合)。"""
    map_file = root / "references" / "index" / "reference-loading-map.md"
    registered: set[str] = set()
    retired: set[str] = set()
    if not map_file.is_file():
        return registered, retired
    text = map_file.read_text(encoding="utf-8")
    for token in _PATH_TOKEN.findall(text):
        registered.add(token)
    # 退役/删除登记行：行内含「退役」「已删除」「删除」字样时，该行路径归入 retired
    for line in text.splitlines():
        if any(word in line for word in ("退役", "已删除", "清理")):
            for token in _PATH_TOKEN.findall(line):
                registered.discard(token)
                retired.add(token)
    return registered, retired


def build_report(root: Path) -> dict:
    assets = _collect_assets(root)
    consumers = _collect_consumers(root)
    referenced, unresolved_tokens = _referenced_assets(root, consumers)

    registered, retired = _load_map_entries(root)
    all_known_refs = set(referenced) | registered | unresolved_tokens

    drift: list[dict[str, str]] = []
    for asset in sorted(assets):
        if any(asset.startswith(d) for d in CODE_CONSUMED_DIRS):
            continue  # 代码/数据驱动消费目录：不判 orphan
        consumers_of_asset = referenced.get(asset, [])
        if consumers_of_asset:
            continue
        if asset in retired:
            continue  # 显式退役：合法状态
        if asset in registered:
            drift.append(
                {
                    "kind": "unwired",
                    "path": asset,
                    "detail": "loading-map 已登记为加载项，但没有任何 skill/agent 引用（登记未接线）",
                }
            )
        else:
            drift.append(
                {
                    "kind": "orphan",
                    "path": asset,
                    "detail": "文件存在但无消费者引用、loading-map 未登记（孤儿未登记）",
                }
            )

    referenced_missing = sorted(
        p for p in all_known_refs if p not in assets and not (root / p).is_file()
    )
    for path in referenced_missing:
        drift.append(
            {
                "kind": "missing",
                "path": path,
                "detail": "被 skill/agent 引用或 loading-map 登记，但文件不存在",
            }
        )

    return {
        "schema_version": _SCHEMA,
        "root": str(root),
        "assets": len(assets),
        "consumers": len(consumers),
        "registered_in_map": len(registered),
        "retired": sorted(retired),
        "ok": not drift,
        "drift": drift,
        "drift_count": len(drift),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="references/templates 引用对账（R15）")
    parser.add_argument("--root", default="", help="插件根目录（缺省自动识别）")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    report = build_report(Path(args.root) if args.root else _plugin_root(None))
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "OK" if report["ok"] else "FAIL"
        print(
            f"{status} reference wiring: assets={report['assets']} consumers={report['consumers']}"
            f" drift={report['drift_count']}"
        )
        for item in report["drift"]:
            print(f"  [{item['kind']}] {item['path']}：{item['detail']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
