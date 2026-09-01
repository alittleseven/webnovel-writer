from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _create_dashboard_client(monkeypatch, project_root: Path) -> TestClient:
    plugin_root = Path(__file__).resolve().parents[2]
    if str(plugin_root) not in sys.path:
        monkeypatch.syspath_prepend(str(plugin_root))

    for name in list(sys.modules):
        if name == "dashboard.app":
            sys.modules.pop(name, None)

    module = importlib.import_module("dashboard.app")
    return TestClient(module.create_app(project_root))


def test_dashboard_cors_allows_localhost_origin(monkeypatch, tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    client = _create_dashboard_client(monkeypatch, tmp_path)

    response = client.options(
        "/api/project/info",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_dashboard_cors_rejects_untrusted_origin(monkeypatch, tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    client = _create_dashboard_client(monkeypatch, tmp_path)

    response = client.options(
        "/api/project/info",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_dashboard_file_read_rejects_large_files(monkeypatch, tmp_path):
    (tmp_path / ".webnovel").mkdir(parents=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    prose_dir = tmp_path / "正文"
    prose_dir.mkdir()
    large_file = prose_dir / "huge.md"
    large_file.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    client = _create_dashboard_client(monkeypatch, tmp_path)

    response = client.get("/api/files/read", params={"path": "正文/huge.md"})

    assert response.status_code == 413


def test_dashboard_db_connects_read_only(monkeypatch, tmp_path):
    """增量审阅 P2-6：dashboard 必须以 mode=ro 只读 URI 连 index.db，不得以读写模式开库。"""
    import sqlite3

    (tmp_path / ".webnovel").mkdir(parents=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    conn = sqlite3.connect(tmp_path / ".webnovel" / "index.db")
    conn.executescript(
        "CREATE TABLE chapters (chapter INTEGER PRIMARY KEY, title TEXT, characters TEXT);"
        "INSERT INTO chapters VALUES (1, '天裂', '[]');"
    )
    conn.commit()
    conn.close()

    captured = {}
    real_connect = sqlite3.connect

    def _spy_connect(*args, **kwargs):
        captured["args"] = (args, kwargs)
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", _spy_connect)
    client = _create_dashboard_client(monkeypatch, tmp_path)

    response = client.get("/api/chapters")

    assert response.status_code == 200
    assert captured, "dashboard 未发起 sqlite 连接"
    conn_args, conn_kwargs = captured["args"]
    assert conn_kwargs.get("uri") is True
    assert "mode=ro" in str(conn_args[0])


def test_server_refuses_nonlocal_bind_without_flag(capsys, monkeypatch, tmp_path):
    """增量审阅 P2-6：--host 非回环且未显式 --allow-nonlocal 时拒绝启动。"""
    stub = types.ModuleType("uvicorn")
    stub.run = lambda **_kwargs: None
    monkeypatch.setitem(sys.modules, "uvicorn", stub)
    monkeypatch.setattr(
        sys, "argv",
        ["server", "--project-root", str(tmp_path), "--host", "0.0.0.0", "--no-browser"],
    )
    plugin_root = Path(__file__).resolve().parents[2]
    if str(plugin_root) not in sys.path:
        monkeypatch.syspath_prepend(str(plugin_root))
    from dashboard import server

    with pytest.raises(SystemExit) as exc:
        server.main()

    assert exc.value.code != 0
    assert "--allow-nonlocal" in capsys.readouterr().err


def test_server_allows_nonlocal_with_explicit_flag(monkeypatch, tmp_path):
    stub = types.ModuleType("uvicorn")
    captured = {}
    stub.run = lambda *args, **kwargs: captured.update(kwargs)
    monkeypatch.setitem(sys.modules, "uvicorn", stub)
    (tmp_path / ".webnovel").mkdir(parents=True)
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv",
        ["server", "--project-root", str(tmp_path), "--host", "0.0.0.0",
         "--allow-nonlocal", "--no-browser"],
    )
    plugin_root = Path(__file__).resolve().parents[2]
    if str(plugin_root) not in sys.path:
        monkeypatch.syspath_prepend(str(plugin_root))
    from dashboard import server

    server.main()

    assert captured.get("host") == "0.0.0.0"
