"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import notification
from api import actuator

def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    reload(notification)


def test_console_notification(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    notification.add_subscription("goal_completed", "console")
    notification.send("goal_completed", {"id": "g1"})
    out = capsys.readouterr().out
    assert "goal_completed" in out


def test_email_notification(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    calls = {}
    def fake_send(to, subject, body):
        calls["to"] = to
    monkeypatch.setattr(actuator, "send_email", fake_send)
    notification.add_subscription("self_patch", "email", "a@b.com")
    notification.send("self_patch", {"note": "hi"})
    assert calls.get("to") == "a@b.com"


def test_event_history(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    notification.send("goal_created", {"id": "g1"})
    events = notification.list_events(1)
    assert events and events[0]["event"] == "goal_created"
