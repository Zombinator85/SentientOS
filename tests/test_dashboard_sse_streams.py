import json
from pathlib import Path

import fastapi
import pytest
from fastapi.testclient import TestClient

from dashboard_ui.api import create_app
from log_utils import append_json
from sentientos.streams.audit_stream import tail_audit_entries


def _collect_sse_events(response, count: int) -> list[dict[str, object]]:
    events = []
    current: dict[str, object] = {"data": []}
    for raw_line in response.iter_lines():
        line = raw_line.decode("utf-8")
        if not line:
            if current["data"]:
                data = json.loads("\n".join(current["data"]))
                events.append(
                    {
                        "id": current.get("id"),
                        "event": current.get("event"),
                        "data": data,
                    }
                )
                if len(events) >= count:
                    break
            current = {"data": []}
            continue
        if line.startswith(":"):
            continue
        if line.startswith("id:"):
            current["id"] = line[3:].strip()
        elif line.startswith("event:"):
            current["event"] = line[6:].strip()
        elif line.startswith("data:"):
            current["data"].append(line[5:].lstrip())
    return events


def _write_pressure_event(log_path: Path, digest: str, event: str) -> None:
    append_json(
        log_path,
        {
            "event": event,
            "digest": digest,
            "signal_type": "drift",
            "as_of_date": "2024-01-01",
            "window_days": 3,
            "severity": "low",
            "counts": {"total": 1},
            "source": "unit-test",
            "enqueued_at": "2024-01-01T00:00:00+00:00",
            "status": "open",
        },
    )


def _write_drift_event(log_path: Path, drift_type: str, date_value: str) -> None:
    append_json(
        log_path,
        {
            "type": "drift_detected",
            "drift_type": drift_type,
            "dates": [date_value],
        },
    )


def test_tail_audit_entries_is_bounded(tmp_path: Path) -> None:
    log_path = tmp_path / "pressure.jsonl"
    for idx in range(3):
        _write_pressure_event(log_path, f"sig-{idx}", "pressure_enqueue")
    entries = tail_audit_entries(log_path, max_lines=2)
    assert len(entries) == 2


def test_pressure_stream_replay_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log_path = tmp_path / "pressure.jsonl"
    monkeypatch.setenv("PRESSURE_QUEUE_LOG", str(log_path))
    for idx in range(3):
        _write_pressure_event(log_path, f"sig-{idx}", "pressure_enqueue")

    client = TestClient(create_app())
    with client.stream("GET", "/api/pressure/stream?limit=2") as response:
        events = _collect_sse_events(response, 2)

    assert len(events) == 2
    payload = events[0]["data"]
    assert payload["stream"] == "pressure"
    assert payload["event_type"] == "pressure_enqueue"
    assert payload["digest"].startswith("sig-")
    assert payload["event_id"] is not None
    assert payload["timestamp"]
    assert "payload" in payload


def test_pressure_stream_limit_cap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log_path = tmp_path / "pressure.jsonl"
    monkeypatch.setenv("PRESSURE_QUEUE_LOG", str(log_path))
    for idx in range(205):
        _write_pressure_event(log_path, f"sig-{idx}", "pressure_enqueue")

    client = TestClient(create_app())
    with client.stream("GET", "/api/pressure/stream?limit=500") as response:
        events = _collect_sse_events(response, 200)

    assert len(events) == 200


def test_drift_stream_replay_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log_path = tmp_path / "drift.jsonl"
    monkeypatch.setenv("DRIFT_DETECTOR_LOG", str(log_path))
    _write_drift_event(log_path, "POSTURE_STUCK", "2024-01-02")
    _write_drift_event(log_path, "PLUGIN_DOMINANCE", "2024-01-01")

    client = TestClient(create_app())
    with client.stream("GET", "/api/drift/stream?limit=1") as response:
        events = _collect_sse_events(response, 1)

    assert len(events) == 1
    payload = events[0]["data"]
    assert payload["event_type"] == "drift_day"
    assert payload["payload"]["date"] in {"2024-01-01", "2024-01-02"}
    assert "summary_counts" in payload["payload"]


def test_stream_disconnect_best_effort(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log_path = tmp_path / "pressure.jsonl"
    monkeypatch.setenv("PRESSURE_QUEUE_LOG", str(log_path))
    _write_pressure_event(log_path, "sig-1", "pressure_enqueue")

    client = TestClient(create_app())
    with client.stream("GET", "/api/pressure/stream?limit=1") as response:
        events = _collect_sse_events(response, 1)
        assert events
