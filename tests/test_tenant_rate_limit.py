import importlib

import sentient_api
import tenant_middleware as tm
from prometheus_client import REGISTRY


def setup_client(monkeypatch):
    monkeypatch.setenv("SENTIENTOS_ALLOW_ANON", "1")
    monkeypatch.setenv("TENANT_RATE_LIMIT", "2")
    importlib.reload(tm)
    REGISTRY._names_to_collectors.clear()
    importlib.reload(sentient_api)
    return sentient_api.app.test_client()


def test_tenant_rate_limit(monkeypatch):
    client = setup_client(monkeypatch)
    h1 = {"X-Sentient-Tenant": "t1"}
    h2 = {"X-Sentient-Tenant": "t2"}
    client.get("/status", headers=h1)
    client.get("/status", headers=h1)
    resp = client.get("/status", headers=h1)
    assert resp.status_code == 429
    resp2 = client.get("/status", headers=h2)
    assert resp2.status_code == 200
