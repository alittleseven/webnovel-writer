#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""webnovel MCP server（stdio，纯标准库）。

ZCode 插件自带 MCP 服务：把 `scripts/webnovel.py` 的只读查询面暴露为结构化工具。
adapter 模式——本文件不复制任何 runtime 逻辑，只做协议适配与子命令转发。

协议：newline-delimited JSON-RPC 2.0（MCP stdio transport）。
清单注册（.zcode-plugin/plugin.json → mcpServers.webnovel）：
    command: python  args: [-X utf8 ${ZCODE_PLUGIN_ROOT}/mcp/server.py]
    env: WEBNOVEL_PLUGIN_ROOT=${ZCODE_PLUGIN_ROOT}
         WEBNOVEL_BOOK_ROOT=${user_config.bookProjectRoot}
         WEBNOVEL_PROJECT_DIR=${CLAUDE_PROJECT_DIR}
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

SERVER_NAME = "webnovel"
SERVER_VERSION = "7.1.0"
PROTOCOL_VERSION = "2024-11-05"
SUBPROCESS_TIMEOUT_SECONDS = 25

_MCP_ROOT = Path(__file__).resolve().parent
_PLUGIN_ROOT = _MCP_ROOT.parent
WEBNOVEL_CLI = _PLUGIN_ROOT / "scripts" / "webnovel.py"


def _plugin_root_from_env() -> Optional[Path]:
    raw = os.environ.get("WEBNOVEL_PLUGIN_ROOT") or os.environ.get("ZCODE_PLUGIN_ROOT")
    if raw and Path(raw).is_dir():
        return Path(raw)
    return None


_DYNAMIC_PLUGIN_ROOT = _plugin_root_from_env()


def _cli_path() -> Path:
    if _DYNAMIC_PLUGIN_ROOT is not None:
        candidate = _DYNAMIC_PLUGIN_ROOT / "scripts" / "webnovel.py"
        if candidate.is_file():
            return candidate
    return WEBNOVEL_CLI


def _workspace_cwd() -> Optional[Path]:
    """宿主会话工作区目录（用于无显式 project_root 时的相对解析）。"""
    raw = os.environ.get("WEBNOVEL_PROJECT_DIR")
    if raw and Path(raw).is_dir():
        return Path(raw)
    return None


def _base_args(project_root: Optional[str]) -> list[str]:
    args: list[str] = []
    if project_root:
        args.extend(["--project-root", project_root])
    return args


# ---------------------------------------------------------------------------
# 工具定义：name / description / inputSchema / 参数 → CLI 子命令构造器
# ---------------------------------------------------------------------------

def _build_where(params: dict[str, Any]) -> list[str]:
    return _base_args(params.get("project_root")) + ["where"]


def _build_project_status(params: dict[str, Any]) -> list[str]:
    args = _base_args(params.get("project_root")) + ["project-status", "--format", "json"]
    if params.get("chapter") is not None:
        args.extend(["--chapter", str(int(params["chapter"]))])
    return args


def _build_doctor(params: dict[str, Any]) -> list[str]:
    args = _base_args(params.get("project_root")) + ["doctor", "--format", "json"]
    if params.get("chapter") is not None:
        args.extend(["--chapter", str(int(params["chapter"]))])
    if params.get("deep"):
        args.append("--deep")
    return args


def _build_setting_read(params: dict[str, Any]) -> list[str]:
    args = _base_args(params.get("project_root")) + ["setting-read", "--name", str(params["name"])]
    if params.get("max_chars") is not None:
        args.extend(["--max-chars", str(int(params["max_chars"]))])
    return args


def _build_timeline_check(params: dict[str, Any]) -> list[str]:
    return _base_args(params.get("project_root")) + [
        "timeline-check",
        "--volume",
        str(params["volume"]),
        "--format",
        "json",
    ]


def _build_meter(params: dict[str, Any]) -> list[str]:
    return _base_args(params.get("project_root")) + ["meter", "report"]


def _build_rag_search(params: dict[str, Any]) -> list[str]:
    args = _base_args(params.get("project_root")) + [
        "rag",
        "search",
        "--query",
        str(params["query"]),
    ]
    if params.get("top_k") is not None:
        args.extend(["--top-k", str(int(params["top_k"]))])
    if params.get("chunk_type"):
        args.extend(["--chunk-type", str(params["chunk_type"])])
    return args


def _build_knowledge(params: dict[str, Any]) -> list[str]:
    mode = params.get("mode", "entity_state")
    subcommand = "query-entity-state" if mode == "entity_state" else "query-relationships"
    return _base_args(params.get("project_root")) + [
        "knowledge",
        subcommand,
        "--entity",
        str(params["entity"]),
        "--at-chapter",
        str(int(params["at_chapter"])),
    ]


def _build_context(params: dict[str, Any]) -> list[str]:
    return _base_args(params.get("project_root")) + [
        "context",
        "--chapter",
        str(int(params["chapter"])),
    ]


# ---------------------------------------------------------------------------
# 治理只读工具（webnovel-copilot-300 M7/T31：M2-M6 治理层的 ZCode 只读面）
# ---------------------------------------------------------------------------


def _build_materials_status(params: dict[str, Any]) -> list[str]:
    args = _base_args(params.get("project_root")) + ["materials", "list", "--format", "json"]
    if params.get("table"):
        for table in params["table"]:
            args.extend(["--table", str(table)])
    return args


def _build_materials_assemble(params: dict[str, Any]) -> list[str]:
    args = _base_args(params.get("project_root")) + ["materials", "assemble", "--format", "json"]
    if params.get("k") is not None:
        args.extend(["--k", str(int(params["k"]))])
    if params.get("table"):
        for table in params["table"]:
            args.extend(["--table", str(table)])
    return args


def _build_power_check(params: dict[str, Any]) -> list[str]:
    args = _base_args(params.get("project_root")) + ["power", "check", "--format", "json"]
    if params.get("chapter") is not None:
        args.extend(["--chapter", str(int(params["chapter"]))])
    return args


def _build_foreshadow_scan(params: dict[str, Any]) -> list[str]:
    args = _base_args(params.get("project_root")) + [
        "foreshadow-scan",
        "scan",
        "--chapter",
        str(int(params["chapter"])),
        "--no-apply",  # MCP 只读面：只报告不标记
        "--format",
        "json",
    ]
    return args


def _build_reader_signals(params: dict[str, Any]) -> list[str]:
    args = _base_args(params.get("project_root")) + ["index", "get-reader-signals", "--limit", "5", "--last-n", "20"]
    return args


_OBJECT_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
_PROJECT_ROOT_PROP = {
    "type": "string",
    "description": "书项目根目录；缺省时按 WEBNOVEL_BOOK_ROOT / 会话工作区向上探测",
}


def _schema(properties: dict[str, Any], required: Optional[list[str]] = None) -> dict[str, Any]:
    merged = dict(properties)
    merged["project_root"] = _PROJECT_ROOT_PROP
    return {
        "type": "object",
        "properties": merged,
        "required": list(required or []),
        "additionalProperties": False,
    }


TOOLS: list[dict[str, Any]] = [
    {
        "name": "webnovel_where",
        "description": "解析并返回当前生效的书项目根目录（定位调试用）。",
        "inputSchema": _schema({}),
        "build": _build_where,
    },
    {
        "name": "webnovel_project_status",
        "description": "机器可读的项目短状态（阶段、断点、计量）。",
        "inputSchema": _schema(
            {"chapter": {"type": "integer", "description": "目标章节号"}},
        ),
        "build": _build_project_status,
    },
    {
        "name": "webnovel_doctor",
        "description": "阶段感知的只读项目体检（目录/文件/JSON/SQLite/RAG/Dashboard）。",
        "inputSchema": _schema(
            {
                "chapter": {"type": "integer", "description": "目标章节号"},
                "deep": {"type": "boolean", "description": "包含 dashboard 等较深检查"},
            },
        ),
        "build": _build_doctor,
    },
    {
        "name": "webnovel_setting_read",
        "description": "读取设定文件原文（如 世界观/力量体系/主角卡）。",
        "inputSchema": _schema(
            {
                "name": {"type": "string", "description": "设定名"},
                "max_chars": {"type": "integer", "description": "最多输出字符（0=全文）"},
            },
            required=["name"],
        ),
        "build": _build_setting_read,
    },
    {
        "name": "webnovel_timeline_check",
        "description": "卷时间线校验（单调递增 / 倒计时算术）。",
        "inputSchema": _schema(
            {"volume": {"type": "string", "description": "卷号"}},
            required=["volume"],
        ),
        "build": _build_timeline_check,
    },
    {
        "name": "webnovel_meter",
        "description": "写章 token 计量只读聚合（读宿主用量库，含子代理）。",
        "inputSchema": _schema({}),
        "build": _build_meter,
    },
    {
        "name": "webnovel_rag_search",
        "description": "章节场景/摘要的语义检索（RAG）。",
        "inputSchema": _schema(
            {
                "query": {"type": "string", "description": "检索 query"},
                "top_k": {"type": "integer", "description": "返回条数（默认 5）"},
                "chunk_type": {"type": "string", "enum": ["scene", "summary"]},
            },
            required=["query"],
        ),
        "build": _build_rag_search,
    },
    {
        "name": "webnovel_knowledge",
        "description": "实体知识查询：指定章节的实体状态或关系。",
        "inputSchema": _schema(
            {
                "mode": {
                    "type": "string",
                    "enum": ["entity_state", "relationships"],
                    "description": "查询模式（默认 entity_state）",
                },
                "entity": {"type": "string", "description": "实体 ID"},
                "at_chapter": {"type": "integer", "description": "目标章节号"},
            },
            required=["entity", "at_chapter"],
        ),
        "build": _build_knowledge,
    },
    {
        "name": "webnovel_context",
        "description": "写前上下文预算与组装预览。",
        "inputSchema": _schema(
            {"chapter": {"type": "integer", "description": "目标章节号"}},
            required=["chapter"],
        ),
        "build": _build_context,
    },
    {
        "name": "webnovel_materials_status",
        "description": "素材活层十表状态（各表条数/active 数，只读）。",
        "inputSchema": _schema(
            {"table": {"type": "array", "items": {"type": "string"}, "description": "限定表名（可多选，缺省全部）"}},
        ),
        "build": _build_materials_status,
    },
    {
        "name": "webnovel_materials_assemble",
        "description": "写作装配预览：定版快照（带版本）+ 活层 active top-K（只读）。",
        "inputSchema": _schema(
            {
                "k": {"type": "integer", "description": "每表活层 top-K（默认 20）"},
                "table": {"type": "array", "items": {"type": "string"}, "description": "限定表名（可多选，缺省全部）"},
            },
        ),
        "build": _build_materials_assemble,
    },
    {
        "name": "webnovel_power_check",
        "description": "战力校验（A2）：跨阶依据/境界链矛盾（high）/通胀曲线（medium）。",
        "inputSchema": _schema(
            {"chapter": {"type": "integer", "description": "只查该章战例（缺省全量）"}},
        ),
        "build": _build_power_check,
    },
    {
        "name": "webnovel_foreshadow_scan",
        "description": "伏笔/承诺逾期扫描（A3，只读报告模式，不标记状态）。",
        "inputSchema": _schema(
            {"chapter": {"type": "integer", "description": "当前章号（扫描基准）"}},
            required=["chapter"],
        ),
        "build": _build_foreshadow_scan,
    },
    {
        "name": "webnovel_reader_signals",
        "description": "追读力信号：近期追读力/钩子分布/爽点统计/审查趋势（只读）。",
        "inputSchema": _schema({}),
        "build": _build_reader_signals,
    },
]

_TOOLS_BY_NAME: dict[str, dict[str, Any]] = {tool["name"]: tool for tool in TOOLS}


# ---------------------------------------------------------------------------
# 子命令执行与结果组装
# ---------------------------------------------------------------------------

def run_webnovel_cli(cli_args: list[str]) -> dict[str, Any]:
    """执行 webnovel.py 子命令并组装 MCP 工具结果。"""
    command = [sys.executable, "-X", "utf8", str(_cli_path()), *cli_args]
    workspace = _workspace_cwd()
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            cwd=str(workspace) if workspace is not None else None,
        )
    except subprocess.TimeoutExpired:
        return {
            "content": [{"type": "text", "text": f"webnovel CLI timed out after {SUBPROCESS_TIMEOUT_SECONDS}s: {' '.join(cli_args[:3])} …"}],
            "isError": True,
        }
    except OSError as exc:
        return {
            "content": [{"type": "text", "text": f"failed to launch webnovel CLI: {exc}"}],
            "isError": True,
        }

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    exit_code = int(proc.returncode or 0)

    text_parts: list[str] = []
    is_json = False
    if stdout:
        try:
            parsed = json.loads(stdout)
            text_parts.append(json.dumps(parsed, ensure_ascii=False, indent=2))
            is_json = True
        except json.JSONDecodeError:
            text_parts.append(stdout)
    if stderr and not is_json:
        text_parts.append(f"[stderr]\n{stderr}")
    if exit_code != 0:
        text_parts.append(f"[exit_code={exit_code}]")

    return {
        "content": [{"type": "text", "text": "\n".join(text_parts) or "(no output)"}],
        "isError": exit_code != 0,
    }


def call_tool(name: str, arguments: Optional[dict[str, Any]]) -> dict[str, Any]:
    tool = _TOOLS_BY_NAME.get(name)
    if tool is None:
        return {
            "content": [{"type": "text", "text": f"unknown tool: {name}"}],
            "isError": True,
        }
    try:
        cli_args = tool["build"](dict(arguments or {}))
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "content": [{"type": "text", "text": f"invalid arguments for {name}: {exc}"}],
            "isError": True,
        }
    return run_webnovel_cli(cli_args)


# ---------------------------------------------------------------------------
# JSON-RPC 分发（newline-delimited stdio）
# ---------------------------------------------------------------------------

def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_request(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    """处理单条 JSON-RPC 消息；通知（无 id）返回 None（不应答）。"""
    method = payload.get("method")
    request_id = payload.get("id")
    params = payload.get("params") or {}

    if request_id is None:
        # notification（如 notifications/initialized）——静默确认即可
        return None

    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(
            request_id,
            {
                "tools": [
                    {
                        "name": tool["name"],
                        "description": tool["description"],
                        "inputSchema": tool["inputSchema"],
                    }
                    for tool in TOOLS
                ]
            },
        )
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str):
            return _error(request_id, -32602, "params.name must be a string")
        result = call_tool(name, params.get("arguments"))
        return _result(request_id, result)

    return _error(request_id, -32601, f"method not found: {method}")


def serve(stream_in: Any, stream_out: Any) -> int:
    for line in stream_in:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            response = _error(None, -32700, "parse error")
        else:
            if not isinstance(payload, dict):
                response = _error(None, -32600, "invalid request")
            else:
                response = handle_request(payload)
        if response is not None:
            stream_out.write(json.dumps(response, ensure_ascii=False) + "\n")
            stream_out.flush()
    return 0


def main() -> int:
    return serve(sys.stdin, sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
