import json

from fastapi.testclient import TestClient

from dashboard_ui import api as dashboard_api


def test_drift_recent_rejects_invalid_n() -> None:
    app = dashboard_api.create_app()
    with TestClient(app) as client:
        response = client.get("/api/drift/recent?n=invalid")

    assert response.status_code == 400
    assert response.json()["detail"] == "n must be a positive integer"


def test_drift_recent_clamps_n(monkeypatch) -> None:
    captured = {}

    def fake_get_recent_drift_reports(limit: int):
        captured["limit"] = limit
        return []

    monkeypatch.setattr(dashboard_api, "get_recent_drift_reports", fake_get_recent_drift_reports)

    app = dashboard_api.create_app()
    with TestClient(app) as client:
        response = client.get("/api/drift/recent?n=999")

    assert response.status_code == 200
    assert response.json() == []
    assert captured["limit"] == 90


def test_drift_silhouette_invalid_payload_returns_422(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_SILHOUETTE_DIR", str(tmp_path))
    payload_path = tmp_path / "2024-01-01.json"
    payload_path.write_text(json.dumps(["bad", "payload"]), encoding="utf-8")

    app = dashboard_api.create_app()
    with TestClient(app) as client:
        response = client.get("/api/drift/silhouette/2024-01-01")

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid silhouette payload"
