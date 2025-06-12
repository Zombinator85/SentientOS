"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import os
import sys
from importlib import reload

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import relay_app
from api import actuator
import pytest


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("RELAY_SECRET", "secret123")
    reload(actuator)
    reload(relay_app)
    return relay_app.app.test_client()


def test_run_shell_allowed(tmp_path, monkeypatch):
    reload(actuator)
    actuator.SANDBOX_DIR = tmp_path / "sb"
    actuator.SANDBOX_DIR.mkdir()
    actuator.WHITELIST = {"shell": ["echo"], "http": ["http://"], "timeout": 5}
    res = actuator.run_shell("echo hello")
    assert res["code"] == 0
    assert "hello" in res["stdout"]


def test_file_write(tmp_path, monkeypatch):
    reload(actuator)
    actuator.SANDBOX_DIR = tmp_path / "sandbox"
    actuator.WHITELIST = {"shell": [], "http": [], "timeout": 5}
    res = actuator.file_write("out.txt", "data")
    written = tmp_path / "sandbox" / "out.txt"
    assert written.exists()
    assert res == {"written": str(written)}


def test_run_shell_blocked():
    reload(actuator)
    actuator.WHITELIST = {"shell": ["echo"], "http": ["http://"], "timeout": 5}
    import pytest
    with pytest.raises(Exception):
        actuator.run_shell("rm -rf /")


def test_act_logging(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload as _reload
    import memory_manager as mm
    _reload(mm)
    _reload(actuator)
    actuator.WHITELIST = {"shell": ["echo"], "http": [], "timeout": 5}
    result = actuator.act({"type": "shell", "cmd": "echo log"})
    assert "log_id" in result
    log_path = tmp_path / "raw" / f"{result['log_id']}.json"
    assert log_path.exists()


def test_http_fetch(monkeypatch):
    reload(actuator)
    actuator.WHITELIST = {"shell": [], "http": ["http://"], "timeout": 5}

    class FakeResp:
        status_code = 200
        text = "ok"

    def fake_request(method, url, **kwargs):
        fake_request.called = (method, url)
        return FakeResp()

    if actuator.requests is None:
        from types import SimpleNamespace
        actuator.requests = SimpleNamespace(request=fake_request)
    else:
        monkeypatch.setattr(actuator.requests, "request", fake_request)
    res = actuator.http_fetch("http://example.com")
    assert res == {"status": 200, "text": "ok"}
    import pytest
    with pytest.raises(Exception):
        actuator.http_fetch("https://blocked.com")


def test_act_route_respects_whitelist(tmp_path, monkeypatch):
    client = setup(tmp_path, monkeypatch)
    actuator.WHITELIST = {"shell": ["echo"], "http": ["http://"], "timeout": 5}

    resp = client.post(
        "/act",
        json={"type": "shell", "cmd": "echo hi"},
        headers={"X-Relay-Secret": "secret123"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "hi" in data.get("stdout", "")
    assert "log_id" in data and "request_log_id" in data

    resp = client.post(
        "/act",
        json={"type": "shell", "cmd": "rm -rf /"},
        headers={"X-Relay-Secret": "secret123"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "error" in data


def test_sandbox_escape(tmp_path, monkeypatch):
    reload(actuator)
    actuator.SANDBOX_DIR = tmp_path / "sbox"
    actuator.SANDBOX_DIR.mkdir()
    with pytest.raises(Exception):
        actuator.file_write("../bad.txt", "oops")


def test_whitelist_pattern(monkeypatch):
    reload(actuator)
    actuator.WHITELIST = {"shell": ["ls*"], "http": [], "timeout": 5}
    res = actuator.run_shell("ls", cwd=".")
    assert res["code"] == 0
    with pytest.raises(Exception):
        actuator.run_shell("rm")


def test_template_expansion(monkeypatch):
    reload(actuator)
    actuator.TEMPLATES = {"greet": {"type": "shell", "cmd": "echo {name}"}}
    actuator.WHITELIST = {"shell": ["echo"], "http": [], "timeout": 5}
    out = actuator.dispatch({"type": "template", "name": "greet", "params": {"name": "Bob"}})
    assert "stdout" in out and "Bob" in out["stdout"]


def test_recent_logs_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload as _reload
    import memory_manager as mm
    _reload(mm)
    _reload(actuator)
    actuator.WHITELIST = {"shell": ["echo"], "http": [], "timeout": 5}
    actuator.act({"type": "shell", "cmd": "echo hi"})
    monkeypatch.setattr(sys, "argv", ["ac", "logs", "--last", "1"])
    actuator.main()
    out = capsys.readouterr().out
    assert "hi" in out


def test_template_prompting(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload as _reload
    import memory_manager as mm
    _reload(mm)
    _reload(actuator)
    actuator.WHITELIST = {"shell": ["echo"], "http": [], "timeout": 5}
    actuator.TEMPLATES = {"note": {"type": "shell", "cmd": "echo {text}"}}

    monkeypatch.setattr(sys, "argv", ["ac", "template", "--name", "note"])
    monkeypatch.setattr("builtins.input", lambda prompt: "test note")
    actuator.main()
    out = capsys.readouterr().out
    assert "log_id" in out


def test_reflection_and_rate_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload as _reload
    import memory_manager as mm
    _reload(mm)
    _reload(actuator)
    actuator.WHITELIST = {"shell": ["echo"], "http": [], "timeout": 5}
    res1 = actuator.act({"type": "shell", "cmd": "echo hi"})
    assert "reflection" in res1
    res2 = actuator.act({"type": "shell", "cmd": "echo hi"})
    assert "error" in res2 and "Rate limit" in res2["error"]


def test_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    import importlib
    import memory_manager as mm
    importlib.reload(mm)
    importlib.reload(actuator)
    actuator.WHITELIST = {"shell": ["echo"], "http": [], "timeout": 5}
    out = actuator.act({"type": "shell", "cmd": "echo hi", "dry_run": True})
    assert out.get("dry_run")


def test_plugin_hello(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("ACT_PLUGINS_DIR", "plugins")
    from importlib import reload as _reload
    import memory_manager as mm
    _reload(mm)
    _reload(actuator)
    out = actuator.dispatch({"type": "hello", "name": "Ada"})
    assert out == {"hello": "Ada"}


def test_template_help_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    import importlib
    import memory_manager as mm
    importlib.reload(mm)
    importlib.reload(actuator)
    actuator.TEMPLATES = {"greet": {"type": "shell", "cmd": "echo {name}"}}
    monkeypatch.setattr(sys, "argv", ["ac", "template_help", "--name", "greet"])
    actuator.main()
    out = capsys.readouterr().out
    assert "required" in out


def test_structured_reflection(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload as _reload
    import memory_manager as mm
    _reload(mm)
    _reload(actuator)
    actuator.WHITELIST = {"shell": ["echo"], "http": [], "timeout": 5}
    res = actuator.act({"type": "shell", "cmd": "echo hi"}, explanation="test", user="bob")
    assert res.get("reflection_id")
    refls = mm.recent_reflections(limit=1)
    assert refls and refls[0]["intent"]["cmd"] == "echo hi"
    assert refls[0]["reason"] == "test"


def test_auto_critique_and_plugin_list(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("ACT_PLUGINS_DIR", "plugins")
    from importlib import reload as _reload
    import memory_manager as mm
    _reload(mm)
    _reload(actuator)
    actuator.WHITELIST = {"shell": ["echo"], "http": [], "timeout": 5}
    res = actuator.act({"type": "shell", "cmd": "rm"})
    assert res["status"] == "failed" and "critique" in res
    monkeypatch.setattr(sys, "argv", ["ac", "plugins"]) 
    actuator.main()
    out = capsys.readouterr().out
    assert "hello" in out
