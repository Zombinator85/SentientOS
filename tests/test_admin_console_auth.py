import importlib
import json
import sys
import types


def _reload(monkeypatch):
    psutil_stub = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "psutil", psutil_stub)
    module = importlib.import_module("relay_app")
    return importlib.reload(module)


def test_admin_endpoints_require_token(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CONSOLE_ENABLED", "1")
    monkeypatch.setenv("ADMIN_ALLOWLIST", "127.0.0.1/32")
    monkeypatch.setenv("NODE_TOKEN", "admin-token")
    monkeypatch.setenv("CSRF_ENABLED", "1")
    module = _reload(monkeypatch)
    module.NODE_TOKEN = "admin-token"
    module.request = types.SimpleNamespace(
        headers={"X-Node-Token": "admin-token"},
        remote_addr="127.0.0.1",
        cookies={},
        get_json=lambda: {},
    )
    status_response = module.admin_status()
    if hasattr(status_response, "get_json"):
        payload = status_response.get_json()
    else:
        raw = status_response.data if hasattr(status_response, "data") else status_response
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw)
    assert payload["role"] == module._ROLE  # type: ignore[attr-defined]
    csrf = payload["csrf_token"]

    module.request = types.SimpleNamespace(
        headers={"X-Node-Token": "admin-token", "X-CSRF-Token": csrf},
        remote_addr="127.0.0.1",
        cookies={},
        get_json=lambda: {"k": 1},
    )
    recall_response = module.admin_memory_recall()
    if hasattr(recall_response, "get_json"):
        data = recall_response.get_json()
    else:
        raw = recall_response.data if hasattr(recall_response, "data") else recall_response
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
    assert "memories" in data
    if data["memories"]:
        assert "text" not in data["memories"][0]
    module.request = types.SimpleNamespace(
        headers={"X-Node-Token": "admin-token"},
        remote_addr="127.0.0.1",
        cookies={},
        get_json=lambda: {},
    )
    summary_response = module.admin_memory_summary()
    if hasattr(summary_response, "get_json"):
        summary = summary_response.get_json()
    else:
        raw = summary_response.data if hasattr(summary_response, "data") else summary_response
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        summary = json.loads(raw)
    assert summary["secure_store"] == module.secure_store.is_enabled()  # type: ignore[attr-defined]


def test_admin_dream_payload(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CONSOLE_ENABLED", "1")
    monkeypatch.setenv("ADMIN_ALLOWLIST", "127.0.0.1/32")
    monkeypatch.setenv("NODE_TOKEN", "admin-token")
    module = _reload(monkeypatch)
    module.NODE_TOKEN = "admin-token"

    monkeypatch.setattr(module.dream_loop, "status", lambda: {
        "active": True,
        "configured": True,
        "interval_minutes": 45,
        "last_cycle": None,
    })

    monkeypatch.setattr(module, "empty_emotion_vector", lambda: {"calm": 0.0, "stress": 0.0, "Neutral": 0.0})
    monkeypatch.setattr(module, "dominant_emotion", lambda vector, neutral_label="Neutral": "calm")
    monkeypatch.setattr(
        module,
        "get_global_state",
        lambda: types.SimpleNamespace(state=lambda: {"calm": 0.62, "stress": 0.18}),
    )

    goal = {
        "id": "goal-3",
        "text": "Finish reflection cycle 3",
        "status": "in_progress",
        "priority": "high",
        "deadline": "2024-01-01T00:00:00Z",
        "progress": 0.4,
        "steps": [{"done": True}, {"done": False}],
    }
    monkeypatch.setattr(module.mm, "next_goal", lambda: goal)

    module.request = types.SimpleNamespace(
        headers={"X-Node-Token": "admin-token"},
        remote_addr="127.0.0.1",
        cookies={},
    )

    response = module.admin_dream()
    if hasattr(response, "get_json"):
        payload = response.get_json()
    else:
        raw = response.data if hasattr(response, "data") else response
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw)

    assert payload["loop"]["active"] is True
    assert payload["loop"]["configured"] is True
    assert payload["loop"]["progress"]["fraction"] == 0.25
    assert payload["mood"]["dominant"] == "calm"
    assert payload["mood"]["vector"]["calm"] == 0.62
    assert payload["pulse"]["level"] == "surge"
    assert payload["pulse"]["intensity"] == 0.62
    assert payload["active_goal"]["text"] == goal["text"]
    assert payload["active_goal"]["progress"]["percent"] == 50.0


def test_reflect_sync_records_remote_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CONSOLE_ENABLED", "1")
    monkeypatch.setenv("ADMIN_ALLOWLIST", "127.0.0.1/32")
    monkeypatch.setenv("NODE_TOKEN", "admin-token")
    module = _reload(monkeypatch)
    module.NODE_TOKEN = "admin-token"
    module._REFLECTION_SYNC_LOG = tmp_path / "reflection_sync.jsonl"
    module._RECENT_REFLECTION_SYNC_IDS.clear()

    record = types.SimpleNamespace(trust_level="trusted")
    monkeypatch.setattr(module.registry, "get", lambda hostname: record if hostname == "trusted-node" else None)

    summary_payload = {"reflection_id": "reflect-42", "headline": "Cycle synced", "importance": 0.55}
    monkeypatch.setattr(module, "decrypt_reflection_payload", lambda payload: dict(summary_payload))

    captured: dict[str, object] = {}

    def fake_append_memory(text, **kwargs):
        captured["text"] = text
        captured["kwargs"] = kwargs

    monkeypatch.setattr(module.mm, "append_memory", fake_append_memory)

    notifications: list[tuple[str, dict]] = []
    monkeypatch.setattr(module, "_notify_admin", lambda event, data=None: notifications.append((event, data or {})))

    envelope = {"nonce": "n", "ciphertext": "c", "encoding": "aesgcm+base64", "summary_id": "reflect-42"}

    module.request = types.SimpleNamespace(
        headers={"X-Node-Token": "admin-token", "X-Node-Id": "trusted-node"},
        get_json=lambda silent=False: envelope,
    )

    response = module.reflect_sync()
    if hasattr(response, "get_json"):
        payload = response.get_json()
    else:
        raw = response.data if hasattr(response, "data") else response
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw)

    assert payload == {"status": "ok"}
    assert list(module._RECENT_REFLECTION_SYNC_IDS) == ["reflect-42"]
    assert module._REFLECTION_SYNC_LOG.exists()

    logged_line = module._REFLECTION_SYNC_LOG.read_text(encoding="utf-8").strip()
    assert logged_line
    logged_summary = json.loads(logged_line)
    assert logged_summary["received_from"] == "trusted-node"
    assert 0.1 <= logged_summary["importance"] <= 1.0

    stored = json.loads(captured["text"])
    assert stored["reflection_sync"]["headline"] == "Cycle synced"
    assert captured["kwargs"]["tags"] == ["reflection", "sync"]
    assert captured["kwargs"]["source"] == "reflection_sync"
    assert notifications == [("refresh", {"source": "reflection_sync", "from": "trusted-node"})]
