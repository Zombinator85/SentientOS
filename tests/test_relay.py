import os
import sys
from importlib import reload

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import relay_app


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
