from pathlib import Path

import pytest

from log_utils import append_json
from sentientos.streams.audit_stream import tail_audit_entries
from sentientos.streams.drift_stream import DriftEventStream
from sentientos.streams.event_stream import ReplayPolicy
from sentientos.streams.pressure_stream import PressureEventStream

pytestmark = pytest.mark.no_legacy_skip


def _write_pressure(log_path: Path, digest: str, event: str, extra: dict | None = None) -> None:
    data = {
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
    }
    if extra:
        data.update(extra)
    append_json(log_path, data)


def _write_drift(log_path: Path, drift_type: str, date_value: str) -> None:
    append_json(
        log_path,
        {
            "type": "drift_detected",
            "drift_type": drift_type,
            "dates": [date_value],
        },
    )


def test_pressure_replay_deterministic_and_cursor(tmp_path: Path) -> None:
    log_path = tmp_path / "pressure.jsonl"
    for idx in range(5):
        _write_pressure(log_path, f"sig-{idx}", "pressure_enqueue")
    stream = PressureEventStream(
        log_path=log_path,
        replay_policy=ReplayPolicy(max_replay_items=10, max_replay_bytes=200_000),
    )
    first = stream.replay(None, limit=3)
    second = stream.replay(None, limit=3)
    assert [item.event_id for item in first] == [item.event_id for item in second]
    cursor = first[-1].event_id
    resumed = stream.replay(cursor, limit=3)
    assert all(int(item.event_id) > int(cursor) for item in resumed)


def test_pressure_payload_allowlist(tmp_path: Path) -> None:
    log_path = tmp_path / "pressure.jsonl"
    _write_pressure(log_path, "sig-1", "pressure_enqueue", extra={"stack": "nope", "raw_log": "nope"})
    stream = PressureEventStream(
        log_path=log_path,
        replay_policy=ReplayPolicy(max_replay_items=5, max_replay_bytes=200_000),
    )
    replay = stream.replay(None, limit=1)
    payload = replay[0]
    assert payload.digest == "sig-1"
    assert "stack" not in payload.payload
    assert "raw_log" not in payload.payload


def test_drift_replay_order_and_bounds(tmp_path: Path) -> None:
    log_path = tmp_path / "drift.jsonl"
    _write_drift(log_path, "POSTURE_STUCK", "2024-01-02")
    _write_drift(log_path, "PLUGIN_DOMINANCE", "2024-01-01")
    stream = DriftEventStream(
        log_path=log_path,
        replay_policy=ReplayPolicy(max_replay_items=7, max_replay_bytes=200_000),
    )
    replay = stream.replay(None, limit=2)
    dates = [item.payload["date"] for item in replay]
    assert dates == sorted(dates, reverse=True)
    assert all("silhouette" not in item.payload for item in replay)


def test_tail_audit_entries_max_bytes(tmp_path: Path) -> None:
    log_path = tmp_path / "pressure.jsonl"
    for idx in range(3):
        _write_pressure(log_path, f"sig-{idx}", "pressure_enqueue")
    entries = tail_audit_entries(log_path, max_lines=3, max_bytes=50)
    assert len(entries) <= 3
