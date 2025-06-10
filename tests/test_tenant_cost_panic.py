import importlib

import sentient_api
import tenant_middleware as tm
from prometheus_client import REGISTRY


def setup_client(monkeypatch):
    monkeypatch.setenv("SENTIENTOS_ALLOW_ANON", "1")
    monkeypatch.setenv("TENANT_DAILY_LIMIT", "1")
    importlib.reload(tm)
    tm._daily_cost.clear()
    REGISTRY._names_to_collectors.clear()
    importlib.reload(sentient_api)
    return sentient_api.app.test_client()


def test_tenant_cost_panic(monkeypatch):
    client = setup_client(monkeypatch)
    tm._daily_cost["t1"] = 2.0
    resp = client.get("/status", headers={"X-Sentient-Tenant": "t1"})
    assert resp.status_code == 503
    resp2 = client.get("/status", headers={"X-Sentient-Tenant": "t2"})
    assert resp2.status_code == 200
