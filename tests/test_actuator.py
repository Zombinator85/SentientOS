import os
import sys
from importlib import reload

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import relay_app
from api import actuator


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("RELAY_SECRET", "secret123")
    reload(actuator)
    reload(relay_app)
    return relay_app.app.test_client()


def test_run_shell_allowed(tmp_path, monkeypatch):
    reload(actuator)
    actuator.WHITELIST = {"shell": ["echo"], "http": ["http://"], "timeout": 5}
    res = actuator.run_shell("echo hello", cwd=tmp_path)
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
