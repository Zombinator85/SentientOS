import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard_ui import api as dashboard_api
from log_utils import append_json
from sentientos.streams.audit_stream import tail_audit_entries


def _collect_sse_events(response, count: int) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
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


def test_pressure_stream_reconnect_no_dupe_and_bounds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "pressure.jsonl"
    monkeypatch.setenv("PRESSURE_QUEUE_LOG", str(log_path))
    for idx in range(205):
        _write_pressure_event(log_path, f"sig-{idx:03d}", "pressure_enqueue")

    all_entries = tail_audit_entries(log_path, max_lines=205)
    tail_entries = tail_audit_entries(log_path, max_lines=200)
    assert len(all_entries) == 205
    assert len(tail_entries) == 200

    client = TestClient(dashboard_api.create_app())
    with client.stream("GET", "/api/pressure/stream?limit=500") as response:
        first_batch = _collect_sse_events(response, 3)

    expected_offsets = [str(offset) for offset, _ in tail_entries]
    assert [event["data"]["event_id"] for event in first_batch] == expected_offsets[:3]
    last_id = first_batch[-1]["data"]["event_id"]

    with client.stream(
        "GET", f"/api/pressure/stream?limit=500&since_id={last_id}"
    ) as response:
        second_batch = _collect_sse_events(response, 2)

    reconnect_ids = [event["data"]["event_id"] for event in second_batch]
    assert reconnect_ids == expected_offsets[3:5]
    assert min(int(value) for value in reconnect_ids) > int(last_id)

    combined_ids = [event["data"]["event_id"] for event in first_batch + second_batch]
    assert len(combined_ids) == len(set(combined_ids))

    allowed_top_keys = {"stream", "schema_version", "event_id", "event_type", "timestamp", "payload", "digest"}
    allowed_payload_keys = {
        "signal_type",
        "as_of_date",
        "window_days",
        "severity",
        "counts",
        "source",
        "enqueued_at",
        "created_at",
        "last_reviewed_at",
        "next_review_due_at",
        "status",
        "closure_reason",
        "closure_note",
        "review_count",
        "persistence_count",
        "reviewed_at",
        "closed_at",
        "actor",
    }
    forbidden_payload_keys = {"raw_log", "stack"}
    for event in first_batch + second_batch:
        payload = event["data"]
        assert set(payload.keys()) == allowed_top_keys
        assert not forbidden_payload_keys.intersection(payload["payload"].keys())
        assert set(payload["payload"].keys()).issubset(allowed_payload_keys)
        assert len(json.dumps(payload)) < 10_000


def test_drift_stream_reconnect_no_dupe_and_payload_bounds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "drift.jsonl"
    monkeypatch.setenv("DRIFT_DETECTOR_LOG", str(log_path))
    _write_drift_event(log_path, "POSTURE_STUCK", "2024-01-02")
    _write_drift_event(log_path, "PLUGIN_DOMINANCE", "2024-01-01")

    client = TestClient(dashboard_api.create_app())
    with client.stream("GET", "/api/drift/stream?limit=2") as response:
        first_batch = _collect_sse_events(response, 1)

    last_date = first_batch[-1]["data"]["payload"]["date"]
    _write_drift_event(log_path, "MOTION_STARVATION", "2024-01-03")

    with client.stream(
        "GET", f"/api/drift/stream?limit=2&since_date={last_date}"
    ) as response:
        second_batch = _collect_sse_events(response, 1)

    combined_dates = [event["data"]["payload"]["date"] for event in first_batch + second_batch]
    assert len(combined_dates) == len(set(combined_dates))
    assert second_batch[0]["data"]["payload"]["date"] > last_date
    for batch in (first_batch, second_batch):
        dates = [event["data"]["payload"]["date"] for event in batch]
        assert dates == sorted(dates, reverse=True)

    allowed_top_keys = {
        "stream",
        "schema_version",
        "event_id",
        "event_type",
        "timestamp",
        "payload",
        "digest",
    }
    forbidden_keys = {"silhouette", "raw_log", "stack"}
    for event in first_batch + second_batch:
        payload = event["data"]
        assert set(payload.keys()).issubset(allowed_top_keys)
        assert not forbidden_keys.intersection(payload["payload"].keys())
        assert len(json.dumps(payload)) < 10_000
