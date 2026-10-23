from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone

import pytest

import sentientos.privilege as privilege


@pytest.fixture
def health_badge(monkeypatch):
    monkeypatch.setattr(privilege, "require_admin_banner", lambda: None)
    monkeypatch.setattr(privilege, "require_lumos_approval", lambda: None)
    module = importlib.import_module("federation_health_badge")
    return importlib.reload(module)


def test_compute_health_counts_nested_peers_and_timezone_aware_recent_events(
    health_badge, tmp_path, monkeypatch
):
    log_path = tmp_path / "federation_log.jsonl"
    now = datetime.now(timezone.utc)
    entries = [
        {"timestamp": now.isoformat(), "data": {"peer": "alpha"}},
        {
            "timestamp": (now - timedelta(days=2)).isoformat(),
            "data": {"peer": "beta"},
        },
    ]
    log_path.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n{malformed\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(health_badge, "LOG_PATH", log_path)

    assert health_badge.compute_health() == {
        "nodes": 2,
        "recent": 1,
        "status": "healthy",
        "source": "configured_local_log_snapshot",
        "window_hours": 24,
        "latest_event_at": now.isoformat().replace("+00:00", "Z"),
        "live_telemetry": False,
        "snapshot_coverage_complete": True,
        "omitted_prefix_bytes": 0,
        "oversized_records_omitted": 0,
    }


def test_compute_health_reports_missing_log(health_badge, tmp_path, monkeypatch):
    monkeypatch.setattr(health_badge, "LOG_PATH", tmp_path / "missing.jsonl")

    assert health_badge.compute_health() == {
        "nodes": 0,
        "recent": 0,
        "status": "no log",
        "source": "configured_local_log_snapshot",
        "window_hours": 24,
        "latest_event_at": None,
        "live_telemetry": False,
        "snapshot_coverage_complete": None,
        "omitted_prefix_bytes": 0,
        "oversized_records_omitted": 0,
    }


def test_compute_health_marks_snapshot_stale_when_latest_event_predates_window(
    health_badge, tmp_path, monkeypatch
):
    log_path = tmp_path / "federation_log.jsonl"
    latest = datetime.now(timezone.utc) - timedelta(days=2)
    log_path.write_text(
        json.dumps({"timestamp": latest.isoformat(), "data": {"peer": "alpha"}}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(health_badge, "LOG_PATH", log_path)

    stats = health_badge.compute_health()

    assert stats["nodes"] == 1
    assert stats["recent"] == 0
    assert stats["status"] == "stale"
    assert stats["live_telemetry"] is False


def test_main_updates_only_requested_health_document(
    health_badge, tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    readme = tmp_path / "README.md"
    original_readme = "Federated instances: **preserve this line**\n"
    readme.write_text(original_readme, encoding="utf-8")

    log_path = tmp_path / "federation_log.jsonl"
    event_at = datetime.now(timezone.utc)
    log_path.write_text(
        json.dumps(
            {
                "timestamp": event_at.isoformat(),
                "data": {"peer": "alpha"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(health_badge, "LOG_PATH", log_path)
    monkeypatch.setattr(
        sys, "argv", ["federation_health_badge.py", "--output", "docs/health.md"]
    )

    health_badge.main()

    assert (tmp_path / "docs/health.md").read_text(encoding="utf-8") == (
        "# Federation Health\n\n"
        "- Nodes in configured log: 1\n"
        "- Events in last 24 hours: 1\n"
        f"- Latest event in log: {event_at.isoformat().replace('+00:00', 'Z')}\n"
        "- Snapshot byte coverage: complete; omitted oldest-prefix bytes: 0; "
        "oversized records skipped: 0\n"
        "- Data source: configured local log snapshot (not live federation telemetry)\n"
        "- Status: healthy\n"
    )
    assert readme.read_text(encoding="utf-8") == original_readme
    assert json.loads(capsys.readouterr().out) == {
        "nodes": 1,
        "recent": 1,
        "status": "healthy",
        "source": "configured_local_log_snapshot",
        "window_hours": 24,
        "latest_event_at": event_at.isoformat().replace("+00:00", "Z"),
        "live_telemetry": False,
        "snapshot_coverage_complete": True,
        "omitted_prefix_bytes": 0,
        "oversized_records_omitted": 0,
    }


def test_future_log_timestamp_is_not_counted_as_recent(health_badge, tmp_path, monkeypatch):
    log_path = tmp_path / "federation_log.jsonl"
    future = datetime.now(timezone.utc) + timedelta(days=1)
    log_path.write_text(
        json.dumps(
            {
                "timestamp": future.isoformat(),
                "data": {"peer": "future-clock"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(health_badge, "LOG_PATH", log_path)

    stats = health_badge.compute_health()

    assert stats["recent"] == 0
    assert stats["status"] == "quiet"
    assert stats["latest_event_at"] == future.isoformat().replace("+00:00", "Z")
    assert stats["live_telemetry"] is False



def test_compute_health_skips_non_object_and_malformed_peer_rows(
    health_badge, tmp_path, monkeypatch
):
    log_path = tmp_path / "federation_log.jsonl"
    log_path.write_text(
        "\n".join(
            [
                "null",
                "[]",
                "17",
                json.dumps(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": {"peer": ["not-hashable"]},
                    }
                ),
                json.dumps({"timestamp": "2025-01-01T00:00:00Z", "data": "invalid"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(health_badge, "LOG_PATH", log_path)

    stats = health_badge.compute_health()

    assert stats["nodes"] == 0
    assert stats["recent"] == 0
    assert stats["latest_event_at"] is None
    assert stats["status"] == "quiet"


@pytest.mark.parametrize(
    "peer_data",
    [
        {},
        {"peer": "unknown"},
        {"peer": " UNKNOWN "},
        {"peer": "   "},
        {"peer": None},
    ],
)
def test_compute_health_does_not_count_recent_events_without_peer_identity(
    health_badge, tmp_path, monkeypatch, peer_data
):
    log_path = tmp_path / "federation_log.jsonl"
    now = datetime.now(timezone.utc)
    log_path.write_text(
        json.dumps({"timestamp": now.isoformat(), "data": peer_data}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(health_badge, "LOG_PATH", log_path)

    assert health_badge.compute_health() == {
        "nodes": 0,
        "recent": 0,
        "status": "quiet",
        "source": "configured_local_log_snapshot",
        "window_hours": 24,
        "latest_event_at": None,
        "live_telemetry": False,
        "snapshot_coverage_complete": True,
        "omitted_prefix_bytes": 0,
        "oversized_records_omitted": 0,
    }


@pytest.mark.parametrize("hours", [0, -1])
def test_compute_health_rejects_non_positive_window(health_badge, hours):
    with pytest.raises(ValueError, match="hours must be positive"):
        health_badge.compute_health(hours)


@pytest.mark.no_legacy_skip
def test_compute_health_handles_positive_window_beyond_timedelta_range(
    health_badge, tmp_path, monkeypatch
):
    event_at = datetime.now(timezone.utc)
    log_path = tmp_path / "federation_log.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "timestamp": event_at.isoformat(),
                "data": {"peer": "large-window"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(health_badge, "LOG_PATH", log_path)

    window_hours = 10**12
    stats = health_badge.compute_health(window_hours)

    assert stats["nodes"] == 1
    assert stats["recent"] == 1
    assert stats["status"] == "healthy"
    assert stats["window_hours"] == window_hours
    assert stats["latest_event_at"] == event_at.isoformat().replace("+00:00", "Z")
    assert stats["live_telemetry"] is False


@pytest.mark.no_legacy_skip
def test_compute_health_bounds_total_snapshot_and_reports_omitted_prefix(
    health_badge, tmp_path, monkeypatch
):
    log_path = tmp_path / "federation_log.jsonl"
    old = datetime.now(timezone.utc) - timedelta(days=2)
    now = datetime.now(timezone.utc)
    events = [
        {"timestamp": old.isoformat(), "data": {"peer": "omitted-old"}},
        {"timestamp": now.isoformat(), "data": {"peer": "omitted-middle"}},
        {"timestamp": now.isoformat(), "data": {"peer": "retained"}},
    ]
    rows = [(json.dumps(event) + "\n").encode("utf-8") for event in events]
    log_path.write_bytes(b"".join(rows))
    monkeypatch.setattr(health_badge, "LOG_PATH", log_path)
    # Keep the final record and five preceding bytes in the tail. This starts
    # inside the middle record, which must be discarded at its newline.
    monkeypatch.setattr(health_badge, "MAX_SNAPSHOT_BYTES", len(rows[2]) + 5)

    stats = health_badge.compute_health()

    assert stats["nodes"] == 1
    assert stats["recent"] == 1
    assert stats["latest_event_at"] == now.isoformat().replace("+00:00", "Z")
    assert stats["status"] == "partial"
    assert stats["snapshot_coverage_complete"] is False
    assert stats["omitted_prefix_bytes"] == len(rows[0]) + len(rows[1])
    assert stats["oversized_records_omitted"] == 0
    assert stats["live_telemetry"] is False


def test_compute_health_skips_invalid_utf8_record_without_losing_valid_rows(
    health_badge, tmp_path, monkeypatch
):
    log_path = tmp_path / "federation_log.jsonl"
    before = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"peer": "before"},
    }
    after = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"peer": "after"},
    }
    log_path.write_bytes(
        json.dumps(before).encode("utf-8")
        + b"\n{\"timestamp\": \"invalid-utf8-\xff\"}\n"
        + json.dumps(after).encode("utf-8")
        + b"\n"
    )
    monkeypatch.setattr(health_badge, "LOG_PATH", log_path)

    stats = health_badge.compute_health()

    assert stats["nodes"] == 2
    assert stats["recent"] == 2
    assert stats["status"] == "healthy"



@pytest.mark.no_legacy_skip
def test_compute_health_skips_ambiguous_or_resource_heavy_json_lines(
    health_badge, tmp_path, monkeypatch
):
    log_path = tmp_path / "federation_log.jsonl"
    now = datetime.now(timezone.utc).isoformat()
    records = [
        (
            '{"timestamp":'
            + json.dumps(now)
            + ',"data":{"peer":"duplicate-first"},"data":{"peer":"duplicate-last"}}'
        ),
        (
            '{"timestamp":'
            + json.dumps(now)
            + ',"data":{"peer":"nested"},"extra":{"state":{"value":1,"value":2}}}'
        ),
        (
            '{"timestamp":'
            + json.dumps(now)
            + ',"data":{"peer":"nan"},"extra":NaN}'
        ),
        (
            '{"timestamp":'
            + json.dumps(now)
            + ',"data":{"peer":"overflow-float"},"extra":1e9999}'
        ),
        (
            '{"timestamp":'
            + json.dumps(now)
            + ',"data":{"peer":"oversized-integer"},"extra":'
            + "9" * (health_badge.MAX_JSON_INTEGER_DIGITS + 1)
            + "}"
        ),
        (
            '{"timestamp":'
            + json.dumps(now)
            + ',"data":{"peer":"deep"},"extra":'
            + "[" * 2000
            + "0"
            + "]" * 2000
            + "}"
        ),
        (
            '{"timestamp":'
            + json.dumps(now)
            + ',"data":{"peer":"overlong"},"padding":"'
            + "x" * health_badge.MAX_RECORD_BYTES
            + '"}'
        ),
        json.dumps({"timestamp": now, "data": {"peer": "valid-after-invalid"}}),
    ]
    log_path.write_text("\n".join(records) + "\n", encoding="utf-8")
    monkeypatch.setattr(health_badge, "LOG_PATH", log_path)

    stats = health_badge.compute_health()

    assert stats["nodes"] == 1
    assert stats["recent"] == 1
    assert stats["status"] == "partial"
    assert stats["latest_event_at"] == now.replace("+00:00", "Z")
    assert stats["snapshot_coverage_complete"] is False
    assert stats["omitted_prefix_bytes"] == 0
    assert stats["oversized_records_omitted"] == 1
    assert stats["live_telemetry"] is False



@pytest.mark.no_legacy_skip
def test_compute_health_does_not_treat_unknown_timestamp_offset_as_utc(
    health_badge, tmp_path, monkeypatch
):
    log_path = tmp_path / "federation_log.jsonl"
    unknown_offset = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "-00:00"
    log_path.write_text(
        json.dumps(
            {
                "timestamp": unknown_offset,
                "data": {"peer": "unknown-offset"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(health_badge, "LOG_PATH", log_path)

    assert health_badge.compute_health() == {
        "nodes": 1,
        "recent": 0,
        "status": "quiet",
        "source": "configured_local_log_snapshot",
        "window_hours": 24,
        "latest_event_at": None,
        "live_telemetry": False,
        "snapshot_coverage_complete": True,
        "omitted_prefix_bytes": 0,
        "oversized_records_omitted": 0,
    }
