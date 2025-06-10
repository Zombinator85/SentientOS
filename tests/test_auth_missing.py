import importlib
import hashlib
from pathlib import Path

import sentient_api
import tenant_middleware as tm
from prometheus_client import REGISTRY


def setup_client(tmp_path, monkeypatch):
    key_file = tmp_path / "keys.yaml"
    token = "secret"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    key_file.write_text(f"tenant1: {token_hash}\n")
    monkeypatch.setenv("SENTIENTOS_KEYS_FILE", str(key_file))
    monkeypatch.delenv("SENTIENTOS_ALLOW_ANON", raising=False)
    importlib.reload(tm)
    REGISTRY._names_to_collectors.clear()
    importlib.reload(sentient_api)
    return sentient_api.app.test_client()


def test_auth_missing(tmp_path, monkeypatch):
    client = setup_client(tmp_path, monkeypatch)
    resp = client.get("/status")
    assert resp.status_code == 401
