from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from dashboard_ui.api import create_app
from sentientos.pressure_queue import (
    PRESSURE_CLOSURE_NOTE_LIMIT,
    close_pressure_signal,
    enqueue_pressure_signal,
    pressure_review_interval,
)

pytestmark = pytest.mark.no_legacy_skip


def _build_signal(digest: str, *, severity: str = "low") -> dict[str, object]:
    return {
        "digest": digest,
        "signal_type": "drift",
        "as_of_date": "2024-01-05",
        "window_days": 3,
        "severity": severity,
        "counts": {"posture_stuck": 2},
        "source": "drift_alerts",
    }


def test_due_listing_defaults_and_bounds(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "pressure_queue.jsonl"
    monkeypatch.setenv("PRESSURE_QUEUE_LOG", str(log_path))
    now = datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc)
    interval = pressure_review_interval("drift", "low")

    for idx in range(205):
        enqueue_pressure_signal(_build_signal(f"digest-{idx}"), now=now)

    app = create_app()
    with TestClient(app) as client:
        due_time = (now + interval).isoformat()
        response_default = client.get("/api/pressure/due", params={"as_of": due_time})
        response_capped = client.get("/api/pressure/due", params={"as_of": due_time, "limit": 999})

    assert response_default.status_code == 200
    assert len(response_default.json()["signals"]) == 50

    assert response_capped.status_code == 200
    assert len(response_capped.json()["signals"]) == 200


def test_revalidate_success_and_conflict_on_closed(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "pressure_queue.jsonl"
    monkeypatch.setenv("PRESSURE_QUEUE_LOG", str(log_path))
    now = datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc)
    interval = pressure_review_interval("drift", "low")
    enqueue_pressure_signal(_build_signal("digest-1"), now=now)

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/pressure/digest-1/revalidate",
            json={"actor": "operator", "as_of": (now + interval).isoformat()},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["signal"]["status"] == "acknowledged"

    close_pressure_signal("digest-1", actor="operator", reason="resolved", note="ok")

    app = create_app()
    with TestClient(app) as client:
        conflict = client.post(
            "/api/pressure/digest-1/revalidate",
            json={"actor": "operator", "as_of": (now + interval).isoformat()},
        )

    assert conflict.status_code == 409


def test_close_validates_reason_and_note_length(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "pressure_queue.jsonl"
    monkeypatch.setenv("PRESSURE_QUEUE_LOG", str(log_path))
    now = datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc)
    enqueue_pressure_signal(_build_signal("digest-2"), now=now)

    app = create_app()
    with TestClient(app) as client:
        invalid_reason = client.post(
            "/api/pressure/digest-2/close",
            json={"actor": "operator", "reason": "invalid_reason", "as_of": now.isoformat()},
        )
        long_note = "n" * (PRESSURE_CLOSURE_NOTE_LIMIT + 1)
        note_too_long = client.post(
            "/api/pressure/digest-2/close",
            json={
                "actor": "operator",
                "reason": "resolved",
                "note": long_note,
                "as_of": now.isoformat(),
            },
        )
        success = client.post(
            "/api/pressure/digest-2/close",
            json={"actor": "operator", "reason": "resolved", "note": "cleared", "as_of": now.isoformat()},
        )

    assert invalid_reason.status_code == 422
    assert note_too_long.status_code == 400
    assert success.status_code == 200


def test_recent_events_bounds(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "pressure_queue.jsonl"
    monkeypatch.setenv("PRESSURE_QUEUE_LOG", str(log_path))
    now = datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc)
    enqueue_pressure_signal(_build_signal("digest-3"), now=now)
    enqueue_pressure_signal(_build_signal("digest-4"), now=now)

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/pressure/recent?limit=1")

    assert response.status_code == 200
    events = response.json()["events"]
    assert len(events) == 1
