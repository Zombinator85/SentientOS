import os
import importlib
import sentient_api


def test_status_coverage(monkeypatch):
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "1")
    importlib.reload(sentient_api)
    with sentient_api.app.test_client() as client:
        resp = client.get("/status")
        data = resp.get_json()
        assert {"uptime", "pending_patches", "cost_today"} <= data.keys()
        assert data["uptime"] < 5

