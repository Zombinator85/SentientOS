import importlib
import json
import sys
from datetime import datetime, timezone
import types


def _reload_app(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CONSOLE_ENABLED", "1")
    monkeypatch.setenv("ADMIN_ALLOWLIST", "127.0.0.1/32")
    monkeypatch.setenv("NODE_TOKEN", "dream-token")
    psutil_stub = types.SimpleNamespace(cpu_percent=lambda interval=0.1: 0.0)
    monkeypatch.setitem(sys.modules, "psutil", psutil_stub)
    module = importlib.reload(importlib.import_module("relay_app"))
    return module


def _decode_response(response):
    if hasattr(response, "get_json"):
        return response.get_json()
    raw = response.data if hasattr(response, "data") else response
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def test_admin_dream_endpoint(monkeypatch, tmp_path):
    module = _reload_app(monkeypatch, tmp_path)

    now = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(
        module.dream_loop,
        "status",
        lambda: {
            "active": False,
            "last_cycle": now,
            "interval_minutes": 30,
            "last_insight": "testing",
        },
        raising=False,
    )
    monkeypatch.setattr(
        module.mm,
        "get_goals",
        lambda open_only=False: [
            {"id": "g1", "status": "completed", "text": "Finish cycle"},
            {"id": "g2", "status": "open", "text": "Reflection follow-up"},
        ],
        raising=False,
    )
    monkeypatch.setattr(
        module.mm,
        "next_goal",
        lambda: {"id": "g2", "status": "open", "text": "Reflection follow-up", "priority": 2},
        raising=False,
    )

    monkeypatch.setattr(
        module,
        "_current_epu_vector",
        lambda: {"Joy": 0.8, "Calm": 0.2},
        raising=False,
    )

    module.request = types.SimpleNamespace(
        headers={"X-Node-Token": "dream-token"},
        remote_addr="127.0.0.1",
        cookies={},
        get_json=lambda: {},
    )

    response = module.admin_dream()
    payload = _decode_response(response)

    assert payload["mood"]["label"] == "Joy"
    assert payload["goal_progress"]["total"] == 2
    assert "emotion_pulse" in payload
    assert payload["loop_progress_percent"] >= 0
