import importlib
import sys
import types


def test_chat_proxy_in_thin_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    psutil_stub = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "psutil", psutil_stub)

    module = importlib.import_module("relay_app")
    monkeypatch.setattr(module, "_ROLE", "thin", raising=False)
    monkeypatch.setattr(module, "_UPSTREAM_CORE", "http://core:5000", raising=False)
    monkeypatch.setattr(module, "_WEBUI_ENABLED", False, raising=False)

    calls = {}

    class DummyResponse:
        status_code = 200

        def json(self):
            return {"reply": "proxied", "routed": "upstream"}

    def fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        calls["url"] = url
        calls["headers"] = headers or {}
        return DummyResponse()

    monkeypatch.setattr(module.requests, "post", fake_post)

    client = module.app.test_client()
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["reply"] == "proxied"
    assert calls["url"].endswith("/chat")
    assert "X-Node-Id" in calls["headers"]
