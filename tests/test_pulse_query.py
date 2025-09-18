from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import pytest

from sentientos import monitor as monitor_module
from sentientos import pulse_query
from sentientos.daemons import pulse_bus
from sentientos.daemons.monitoring_daemon import MonitoringDaemon


@pytest.fixture
def ledger_path(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "codex.jsonl"
    monkeypatch.setenv("CODEX_LEDGER_PATH", str(path))
    monkeypatch.setattr(pulse_query, "_LEDGER_PATH", path)
    return path


def _publish_event(timestamp: datetime, priority: str, daemon: str, event_type: str) -> None:
    pulse_bus.publish(
        {
            "timestamp": timestamp.isoformat(),
            "priority": priority,
            "source_daemon": daemon,
            "event_type": event_type,
            "payload": {"details": event_type},
        }
    )


@pytest.fixture(autouse=True)
def reset_bus() -> None:
    pulse_bus.reset()
    yield
    pulse_bus.reset()


def _create_monitor(tmp_path, monkeypatch, query_config=None) -> MonitoringDaemon:
    glow_root = tmp_path / "glow" / "monitoring"
    glow_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MONITORING_GLOW_ROOT", str(glow_root))
    monkeypatch.delenv("MONITORING_METRICS_PATH", raising=False)
    monkeypatch.delenv("MONITORING_ALERTS_PATH", raising=False)
    monkeypatch.setattr(pulse_query, "_METRICS_PATH", glow_root / "metrics.jsonl")
    return MonitoringDaemon(snapshot_interval=timedelta(0), query_http_config=query_config)


def test_get_events_applies_filters(ledger_path) -> None:
    now = datetime.now(timezone.utc)
    _publish_event(now - timedelta(hours=2), "critical", "NetworkDaemon", "offline")
    _publish_event(now - timedelta(minutes=45), "critical", "NetworkDaemon", "outage")
    _publish_event(now - timedelta(minutes=30), "info", "NetworkDaemon", "heartbeat")
    _publish_event(now - timedelta(minutes=20), "critical", "StorageDaemon", "disk_full")

    since = now - timedelta(hours=1)
    events = pulse_query.get_events(since, {"priority": "critical", "source_daemon": "NetworkDaemon"})
    assert len(events) == 1
    assert events[0]["event_type"] == "outage"


def test_get_metrics_reads_signed_snapshot(tmp_path, monkeypatch, ledger_path) -> None:
    monitor = _create_monitor(tmp_path, monkeypatch)
    try:
        now = datetime.now(timezone.utc)
        _publish_event(now - timedelta(minutes=5), "warning", "NetworkDaemon", "latency")
        _publish_event(now - timedelta(minutes=3), "warning", "NetworkDaemon", "latency")
        monitor.persist_snapshot()

        metrics = pulse_query.get_metrics("24h", {"priority": "warning"})
        assert metrics["window"] == "24h"
        summary = metrics["summary"]
        assert summary["total_events"] == 2
        assert summary["priority"] == {"warning": 2}
        assert metrics["verified_snapshots"], "expected verified snapshot timestamps"
    finally:
        monitor.stop()


def _fetch_json(url: str, *, timeout: float = 5.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.URLError as exc:  # pragma: no cover - transient startup
            last_exc = exc
            time.sleep(0.05)
    if last_exc is not None:  # pragma: no cover - should not happen
        raise last_exc
    raise RuntimeError(f"Failed to fetch {url}")


def test_cli_outputs_summary(tmp_path, monkeypatch, capsys, ledger_path) -> None:
    monitor = _create_monitor(tmp_path, monkeypatch)
    try:
        now = datetime.now(timezone.utc)
        _publish_event(now - timedelta(minutes=10), "critical", "NetworkDaemon", "outage")
        monitor.persist_snapshot()

        exit_code = monitor_module.main([
            "query",
            "--last",
            "1h",
            "--priority",
            "critical",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Pulse Query Summary" in captured.out
        assert "Matched events: 1" in captured.out
        assert "Total events: 1" in captured.out
        assert "Anomalies: none" in captured.out
        assert captured.err == ""
    finally:
        monitor.stop()


def test_http_endpoint_enabled_and_disabled(tmp_path, monkeypatch, ledger_path) -> None:
    monitor_enabled = _create_monitor(
        tmp_path,
        monkeypatch,
        query_config={"query_http_enabled": True, "query_http_port": 0},
    )
    try:
        now = datetime.now(timezone.utc)
        _publish_event(now - timedelta(minutes=15), "critical", "NetworkDaemon", "outage")
        monitor_enabled.persist_snapshot()

        host = monitor_enabled.query_http_host or "127.0.0.1"
        port = monitor_enabled.query_http_port
        assert port is not None

        params = urlencode({"last": "1h", "priority": "critical"})
        events_url = f"http://{host}:{port}/query/events?{params}"
        events_payload = _fetch_json(events_url)
        assert events_payload["count"] == 1
        assert events_payload["filters"] == {"priority": "critical"}
        assert events_payload["events"][0]["event_type"] == "outage"

        metrics_url = f"http://{host}:{port}/query/metrics?{urlencode({'window': '24h'})}"
        metrics_payload = _fetch_json(metrics_url)
        assert metrics_payload["window"] == "24h"
        assert metrics_payload["summary"]["total_events"] == 1
    finally:
        monitor_enabled.stop()

    monitor_disabled = _create_monitor(
        tmp_path,
        monkeypatch,
        query_config={"query_http_enabled": False, "query_http_port": 0},
    )
    try:
        host = monitor_disabled.query_http_host or "127.0.0.1"
        port = monitor_disabled.query_http_port
        assert port is not None

        disabled_url = f"http://{host}:{port}/query/events?{urlencode({'last': '1h'})}"
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(disabled_url, timeout=5)
        assert excinfo.value.code == 403
    finally:
        monitor_disabled.stop()


def test_query_logging_writes_ledger(tmp_path, monkeypatch, ledger_path) -> None:
    monitor = _create_monitor(tmp_path, monkeypatch)
    try:
        now = datetime.now(timezone.utc)
        _publish_event(now - timedelta(minutes=5), "critical", "NetworkDaemon", "outage")
        monitor.persist_snapshot()
    finally:
        monitor.stop()

    since = datetime.now(timezone.utc) - timedelta(hours=1)
    events = pulse_query.get_events(since, {"priority": "critical"})
    assert len(events) == 1

    metrics = pulse_query.get_metrics("24h", {"priority": "critical"})
    assert metrics["summary"]["total_events"] == 1

    entries = []
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                entries.append(json.loads(line))

    assert [entry["query"] for entry in entries] == ["events", "metrics"]
    events_entry = entries[0]
    assert events_entry["requester"] == "local"
    assert events_entry["count"] == 1
    assert events_entry["filters"]["priority"] == "critical"
    assert "since" in events_entry["filters"]

    metrics_entry = entries[1]
    assert metrics_entry["requester"] == "local"
    assert metrics_entry["filters"]["priority"] == "critical"
    assert metrics_entry["filters"]["window"] == "24h"
    assert metrics_entry["count"] == 1
