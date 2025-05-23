import json
import types

import pytest
from flask import Flask

import sentientos_relay as sr


@pytest.fixture(autouse=True)
def setup_env(monkeypatch, tmp_path):
    monkeypatch.setenv("RELAY_SECRET", "s3cr3t")
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    monkeypatch.setenv("TOGETHER_API_KEY", "key")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama")
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "mem"))
    # reload modules to pick up env vars
    import importlib
    import memory_manager as mm
    importlib.reload(mm)
    importlib.reload(sr)
    yield


def fake_response(status=200, json_data=None, text=""):
    resp = types.SimpleNamespace()
    resp.status_code = status
    resp.text = text
    resp.json = lambda: json_data
    return resp


def test_relay_success(monkeypatch):
    def fake_post(*args, **kwargs):
        return fake_response(json_data={"choices": [{"message": {"content": "hi"}}]})

    monkeypatch.setattr(sr.requests, "post", fake_post)
    monkeypatch.setattr(sr, "write_mem", lambda *a, **k: None)

    client = sr.app.test_client()
    res = client.post(
        "/relay",
        json={"message": "hello", "model": sr.GPT4_MODEL},
        headers={"X-Relay-Secret": "s3cr3t"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["reply_chunks"] == ["hi"]


def test_relay_invalid_secret():
    client = sr.app.test_client()
    res = client.post(
        "/relay",
        json={"message": "hi", "model": sr.GPT4_MODEL},
        headers={"X-Relay-Secret": "wrong"},
    )
    assert res.status_code == 403


def test_relay_missing_json(monkeypatch):
    client = sr.app.test_client()
    res = client.post("/relay", headers={"X-Relay-Secret": "s3cr3t"})
    assert res.status_code >= 400
