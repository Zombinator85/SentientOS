import os
import sys
import json
import time
import pytest
from importlib import reload
from pathlib import Path


import sentientos.openai_connector as openai_connector
from sentientos.flask_stub import Request


def setup_app(tmp_path, monkeypatch):
    monkeypatch.setenv("CONNECTOR_TOKEN", "token123")
    monkeypatch.setenv("OPENAI_CONNECTOR_LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("SSE_TIMEOUT", "0.2")
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


def test_message_missing_token(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    resp = client.post(
        "/message",
        json={"text": "hi"},
        headers={},
    )
    assert resp.status_code == 403


def test_message_malformed_json(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    resp = client.post(
        "/message",
        json=None,
        headers={"Authorization": "Bearer token123"},
    )
    assert resp.status_code == 400


def test_message_invalid_type(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    resp = client.post(
        "/message",
        json={"text": 123},
        headers={"Authorization": "Bearer token123"},
    )
    assert resp.status_code == 400


def test_message_missing_field(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    resp = client.post(
        "/message",
        json={},
        headers={"Authorization": "Bearer token123"},
    )
    assert resp.status_code == 400


def test_sse_authorized(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    openai_connector._events.put(json.dumps({"time": time.time(), "data": "test"}))
    openai_connector.request = Request(None, {"Authorization": "Bearer token123"})
    resp = openai_connector.sse()
    status = resp.status_code if hasattr(resp, "status_code") else resp[1]
    assert status == 200
    assert next(resp.data).startswith("data: ")


def test_sse_invalid_token(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    openai_connector.request = Request(None, {"Authorization": "Bearer wrong"})
    resp = openai_connector.sse()
    status = resp[1] if isinstance(resp, tuple) else resp.status_code
    assert status == 403


def test_sse_missing_token(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    openai_connector.request = Request(None, {})
    resp = openai_connector.sse()
    status = resp[1] if isinstance(resp, tuple) else resp.status_code
    assert status == 403


def test_sse_multiple_clients(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    openai_connector._events.put(json.dumps({"time": time.time(), "data": {"a": 1}}))
    openai_connector._events.put(json.dumps({"time": time.time(), "data": {"b": 2}}))
    openai_connector.request = Request(None, {"Authorization": "Bearer token123"})
    gen1 = openai_connector.sse().data
    openai_connector.request = Request(None, {"Authorization": "Bearer token123"})
    gen2 = openai_connector.sse().data
    first1 = next(gen1)
    first2 = next(gen2)
    assert first1.startswith("data: ")
    assert first2.startswith("data: ")


def test_sse_disconnect(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    openai_connector._events.put(json.dumps({"time": time.time(), "data": {"x": 1}}))
    openai_connector.request = Request(None, {"Authorization": "Bearer token123"})
    resp = openai_connector.sse()
    gen = resp.data
    next(gen)
    gen.close()
    with pytest.raises(StopIteration):
        next(gen)

def test_healthz_and_metrics(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    resp = openai_connector.healthz()
    if hasattr(resp, "status_code"):
        assert resp.status_code == 200
        body = json.loads(resp.data)
    else:
        assert isinstance(resp, str)
        body = json.loads(resp)
    assert body["status"] == "ok"

    openai_connector.request = Request(None, {"Authorization": "Bearer token123"})
    openai_connector._events.put(json.dumps({"time": time.time(), "data": {"x": 1}}))
    resp_sse = openai_connector.sse()
    next(resp_sse.data)

    metrics = openai_connector.metrics().data
    if isinstance(metrics, bytes):
        metrics = metrics.decode()
    assert "connections_total" in metrics
    assert "events_total" in metrics

def test_schema_violation_logged(tmp_path, monkeypatch):
    client = setup_app(tmp_path, monkeypatch)
    client.post(
        "/message",
        json={},
        headers={"Authorization": "Bearer token123"},
    )
    log_path = Path(os.getenv("OPENAI_CONNECTOR_LOG"))
    lines = [json.loads(x) for x in log_path.read_text().splitlines() if x.strip()]
    assert any(e["event"] == "schema_violation" for e in lines)

