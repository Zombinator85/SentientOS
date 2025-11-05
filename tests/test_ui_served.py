import importlib
import sys
import types


def test_webui_index_served(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_ROLE", "core")
    monkeypatch.setenv("WEBUI_ENABLED", "1")

    psutil_stub = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "psutil", psutil_stub)

    module = importlib.import_module("relay_app")
    response = module.webui_root()
    assert getattr(response, "status_code", 200) == 200
    body = response.data if hasattr(response, "data") else response
    if isinstance(body, bytes):
        assert b"SentientOS Thin Console" in body
    else:
        assert "SentientOS Thin Console" in body

    module.request.headers = {"X-Relay-Secret": module.RELAY_SECRET}
    nodes = module.nodes_list_ui()
    assert getattr(nodes, "status_code", 200) == 200

    # Restore defaults to avoid leaking configuration.
    monkeypatch.setenv("SENTIENTOS_ROLE", "core")
    monkeypatch.delenv("WEBUI_ENABLED", raising=False)
    importlib.reload(module)
