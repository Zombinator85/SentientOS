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
