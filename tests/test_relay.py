"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import sys
from importlib import reload

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import relay_app
import time


def setup_app(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("RELAY_SECRET", "secret123")
    reload(relay_app)
    return relay_app.app.test_client()


def test_relay_success(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    resp = client.post(
        "/relay",
        json={"message": "hi", "model": "test"},
        headers={"X-Relay-Secret": "secret123"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["reply_chunks"] == ["Echo: hi (test)"]


def test_relay_forbidden(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    resp = client.post(
        "/relay",
        json={"message": "hi"},
        headers={"X-Relay-Secret": "wrong"},
    )
    assert resp.status_code == 403


def test_act_async_status(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    from api import actuator
    actuator.WHITELIST = {"shell": ["echo"], "http": [], "timeout": 5}

    resp = client.post(
        "/act",
        json={"type": "shell", "cmd": "echo hi", "async": True},
        headers={"X-Relay-Secret": "secret123"},
    )
    data = resp.get_json()
    assert data["status"] == "queued"
    aid = data["action_id"]

    # poll status
    for _ in range(5):
        resp2 = client.post("/act_status", json={"id": aid}, headers={"X-Relay-Secret": "secret123"})
        status = resp2.get_json()
        if status.get("status") == "finished":
            break
        time.sleep(0.1)
    assert status.get("status") == "finished"


def test_goal_api(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    resp = client.post(
        "/goals/add",
        json={"text": "demo", "intent": {"type": "hello", "name": "Ada"}},
        headers={"X-Relay-Secret": "secret123"},
    )
    goal = resp.get_json()
    assert goal.get("text") == "demo"
    gid = goal["id"]
    client.post("/agent/run", json={"cycles": 1}, headers={"X-Relay-Secret": "secret123"})
    resp = client.post("/goals/complete", json={"id": gid}, headers={"X-Relay-Secret": "secret123"})
    assert resp.status_code == 200
