import os
import sys
from importlib import reload

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import openai_connector


def setup_app(tmp_path, monkeypatch):
    monkeypatch.setenv("CONNECTOR_TOKEN", "token123")
    reload(openai_connector)
    return openai_connector.app.test_client()


def test_message_authorized(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    resp = client.post(
        "/message",
        json={"text": "hi"},
        headers={"Authorization": "Bearer token123"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "queued"


def test_message_forbidden(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    resp = client.post(
        "/message",
        json={"text": "hi"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 403
