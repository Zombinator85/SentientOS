import importlib

from fastapi.testclient import TestClient


def test_admin_status_and_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    import sentientos.admin_server as admin_server

    admin_server = importlib.reload(admin_server)
    client = TestClient(admin_server.APP)

    status = client.get("/admin/status")
    assert status.status_code == 200
    body = status.json()
    assert "modules" in body

    metrics = client.get("/admin/metrics")
    assert metrics.status_code == 200
    assert "sos" in metrics.text
