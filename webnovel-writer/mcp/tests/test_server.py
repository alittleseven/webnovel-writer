#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _ensure_mcp_on_path() -> None:
    mcp_dir = Path(__file__).resolve().parents[1]
    if str(mcp_dir) not in sys.path:
        sys.path.insert(0, str(mcp_dir))


_ensure_mcp_on_path()

import server  # noqa: E402


class _FakeCompleted:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


# ---------------------------------------------------------------------------
# 协议层
# ---------------------------------------------------------------------------

def test_initialize_handshake():
    response = server.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}}
    )
    assert response["id"] == 1
    result = response["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == "webnovel"


def test_ping_returns_empty_result():
    response = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "ping"})
    assert response["result"] == {}


def test_notification_gets_no_response():
    assert server.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_unknown_method_returns_error():
    response = server.handle_request({"jsonrpc": "2.0", "id": 3, "method": "no/such"})
    assert response["error"]["code"] == -32601


def test_tools_list_contains_fourteen_tools():
    response = server.handle_request({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
    tools = response["result"]["tools"]
    assert len(tools) == 14, "M7/T31：9 基础 + 5 治理只读工具"
    names = {tool["name"] for tool in tools}
    assert "webnovel_where" in names
    assert "webnovel_doctor" in names
    assert "webnovel_rag_search" in names
    assert {
        "webnovel_materials_status",
        "webnovel_materials_assemble",
        "webnovel_power_check",
        "webnovel_foreshadow_scan",
        "webnovel_reader_signals",
    } <= names, "T31 五个治理只读工具"
    for tool in tools:
        assert tool["inputSchema"]["type"] == "object"
        assert "project_root" in tool["inputSchema"]["properties"]


# ---------------------------------------------------------------------------
# 工具 → CLI 子命令映射
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name,arguments,expected_fragment",
    [
        ("webnovel_where", {}, ["where"]),
        ("webnovel_project_status", {}, ["project-status", "--format", "json"]),
        ("webnovel_project_status", {"chapter": 12}, ["--chapter", "12"]),
        ("webnovel_doctor", {"deep": True}, ["doctor", "--deep", "--format", "json"]),
        ("webnovel_setting_read", {"name": "世界观"}, ["setting-read", "--name", "世界观"]),
        ("webnovel_timeline_check", {"volume": "1"}, ["timeline-check", "--volume", "1", "--format", "json"]),
        ("webnovel_meter", {}, ["meter", "report"]),
        ("webnovel_rag_search", {"query": "主角 突破"}, ["rag", "search", "--query", "主角 突破"]),
        ("webnovel_rag_search", {"query": "x", "top_k": 3}, ["--top-k", "3"]),
        ("webnovel_knowledge", {"entity": "E1", "at_chapter": 5}, ["knowledge", "query-entity-state", "--entity", "E1", "--at-chapter", "5"]),
        ("webnovel_knowledge", {"entity": "E1", "at_chapter": 5, "mode": "relationships"}, ["query-relationships"]),
        ("webnovel_context", {"chapter": 30}, ["context", "--chapter", "30"]),
        ("webnovel_materials_status", {}, ["materials", "list", "--format", "json"]),
        ("webnovel_materials_status", {"table": ["桥段"]}, ["--table", "桥段"]),
        ("webnovel_materials_assemble", {"k": 5, "table": ["桥段", "梗与反差"]}, ["assemble", "--k", "5"]),
        ("webnovel_power_check", {}, ["power", "check", "--format", "json"]),
        ("webnovel_power_check", {"chapter": 37}, ["--chapter", "37"]),
        ("webnovel_foreshadow_scan", {"chapter": 60}, ["foreshadow-scan", "scan", "--chapter", "60", "--no-apply"]),
        ("webnovel_reader_signals", {}, ["index", "get-reader-signals", "--limit", "5"]),
    ],
)
def test_tool_builders_map_to_cli(name, arguments, expected_fragment):
    tool = server._TOOLS_BY_NAME[name]
    cli_args = tool["build"](dict(arguments))
    for token in expected_fragment:
        assert token in cli_args


def test_project_root_prepended_as_global_flag():
    tool = server._TOOLS_BY_NAME["webnovel_where"]
    cli_args = tool["build"]({"project_root": r"D:\books\novel"})
    assert cli_args[:3] == ["--project-root", r"D:\books\novel", "where"]


def test_tools_call_unknown_tool(monkeypatch):
    monkeypatch.setattr(server.subprocess, "run", None)  # 不应触达子进程
    result = server.call_tool("no_such_tool", {})
    assert result["isError"] is True
    assert "unknown tool" in result["content"][0]["text"]


def test_tools_call_invalid_arguments(monkeypatch):
    monkeypatch.setattr(server.subprocess, "run", None)
    result = server.call_tool("webnovel_setting_read", {})  # 缺必填 name
    assert result["isError"] is True
    assert "invalid arguments" in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# 子进程执行分支（mock subprocess.run）
# ---------------------------------------------------------------------------

def _capture_command(monkeypatch, fake):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return fake

    monkeypatch.setattr(server.subprocess, "run", fake_run)
    return captured


def test_tools_call_json_output_passthrough(monkeypatch):
    captured = _capture_command(
        monkeypatch, _FakeCompleted(stdout='{"status": "ok", "chapters": 38}')
    )
    result = server.call_tool("webnovel_project_status", {})

    assert result["isError"] is False
    assert json.loads(result["content"][0]["text"]) == {"status": "ok", "chapters": 38}
    assert captured["command"][1:3] == ["-X", "utf8"]
    assert captured["command"][3].endswith("webnovel.py")
    assert captured["command"][4] == "project-status"
    assert captured["kwargs"]["timeout"] == server.SUBPROCESS_TIMEOUT_SECONDS


def test_tools_call_plain_text_output(monkeypatch):
    _capture_command(monkeypatch, _FakeCompleted(stdout="D:\\books\\novel"))
    result = server.call_tool("webnovel_where", {})
    assert result["content"][0]["text"] == "D:\\books\\novel"
    assert result["isError"] is False


def test_tools_call_nonzero_exit_marks_error(monkeypatch):
    _capture_command(monkeypatch, _FakeCompleted(stdout="", stderr="boom", returncode=1))
    result = server.call_tool("webnovel_where", {})
    assert result["isError"] is True
    assert "boom" in result["content"][0]["text"]
    assert "[exit_code=1]" in result["content"][0]["text"]


def test_tools_call_timeout(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr(server.subprocess, "run", fake_run)
    result = server.call_tool("webnovel_doctor", {})
    assert result["isError"] is True
    assert "timed out" in result["content"][0]["text"]


def test_tools_call_launch_failure(monkeypatch):
    def fake_run(command, **kwargs):
        raise OSError("spawn failed")

    monkeypatch.setattr(server.subprocess, "run", fake_run)
    result = server.call_tool("webnovel_where", {})
    assert result["isError"] is True
    assert "failed to launch" in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# serve() 主循环
# ---------------------------------------------------------------------------

def test_serve_dispatches_lines():
    import io

    requests = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
            "",
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            "not-json",
        ]
    )
    stdout = io.StringIO()
    code = server.serve(io.StringIO(requests + "\n"), stdout)
    assert code == 0
    lines = [json.loads(line) for line in stdout.getvalue().strip().splitlines()]
    assert len(lines) == 2  # ping 响应 + parse error；通知无响应
    assert lines[0]["result"] == {}
    assert lines[1]["error"]["code"] == -32700
