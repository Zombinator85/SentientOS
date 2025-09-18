import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Tuple

import pytest

from sentientos.daemons import pulse_bus
from sentientos.daemons.monitoring_daemon import AnomalyThreshold, MonitoringDaemon


def _build_event(
    event_type: str,
    *,
    priority: str = "info",
    source: str = "NetworkDaemon",
) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": source,
        "event_type": event_type,
        "priority": priority,
        "payload": {"event": event_type},
    }


@pytest.fixture(autouse=True)
def reset_bus() -> Iterable[None]:
    pulse_bus.reset()
    yield
    pulse_bus.reset()


@pytest.fixture
def monitor_factory(tmp_path, monkeypatch) -> Iterable[Tuple[Callable[..., MonitoringDaemon], Path, Path]]:
    glow_root = tmp_path / "glow" / "monitoring"
    glow_root.mkdir(parents=True, exist_ok=True)
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MONITORING_GLOW_ROOT", str(glow_root))
    monkeypatch.delenv("MONITORING_METRICS_PATH", raising=False)
    monkeypatch.delenv("MONITORING_ALERTS_PATH", raising=False)
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(logs_dir))

    monitors: list[MonitoringDaemon] = []

    def factory(**kwargs) -> MonitoringDaemon:
        monitor = MonitoringDaemon(snapshot_interval=timedelta(0), **kwargs)
        monitors.append(monitor)
        return monitor

    yield factory, glow_root, logs_dir

    for monitor in monitors:
        monitor.stop()


def test_event_aggregation_tracks_counts(monitor_factory) -> None:
    factory, glow_root, _ = monitor_factory
    monitor = factory()

    pulse_bus.publish(_build_event("info_ping", priority="info", source="NetworkDaemon"))
    pulse_bus.publish(_build_event("latency", priority="warning", source="NetworkDaemon"))
    pulse_bus.publish(_build_event("disk", priority="warning", source="StorageDaemon"))
    pulse_bus.publish(_build_event("outage", priority="critical", source="NetworkDaemon"))

    metrics = monitor.current_metrics()
    overall = metrics["overall"]
    assert overall["total_events"] == 4
    assert overall["priority"] == {"critical": 1, "info": 1, "warning": 2}
    assert overall["source_daemon"]["NetworkDaemon"] == 3
    assert overall["per_daemon"]["NetworkDaemon"]["priority"]["warning"] == 1
    assert overall["per_daemon"]["NetworkDaemon"]["matrix"]["critical"]["outage"] == 1

    window_metrics = metrics["windows"]["1m"]
    assert window_metrics["total_events"] == 4
    assert window_metrics["rate_per_minute"] >= 4.0
    assert (glow_root / "metrics.jsonl").exists() is False


def test_anomaly_detection_triggers_alert(monitor_factory) -> None:
    factory, glow_root, logs_dir = monitor_factory
    threshold = AnomalyThreshold(priority="critical", limit=2, window=timedelta(minutes=10), name="burst")
    monitor = factory(anomaly_thresholds=[threshold])

    captured: list[dict] = []
    subscription = pulse_bus.subscribe(captured.append, priorities=["critical"])
    try:
        pulse_bus.publish(_build_event("critical_1", priority="critical", source="NetworkDaemon"))
        pulse_bus.publish(_build_event("critical_2", priority="critical", source="NetworkDaemon"))
        pulse_bus.publish(_build_event("critical_3", priority="critical", source="NetworkDaemon"))
    finally:
        subscription.unsubscribe()

    assert any(evt["event_type"] == "monitor_alert" for evt in captured)
    assert monitor.anomalies and monitor.anomalies[-1]["observed"] == 3

    alerts_path = glow_root / "alerts.jsonl"
    assert alerts_path.exists()
    alerts = [json.loads(line) for line in alerts_path.read_text().splitlines() if line]
    assert alerts[-1]["source_daemon"] == "NetworkDaemon"

    ledger_path = logs_dir / "monitoring_alerts.jsonl"
    assert ledger_path.exists() and ledger_path.stat().st_size > 0


def test_snapshot_persistence_and_signature(monitor_factory) -> None:
    factory, glow_root, _ = monitor_factory
    monitor = factory()
    pulse_bus.publish(_build_event("warning", priority="warning", source="NetworkDaemon"))

    snapshot = monitor.persist_snapshot()
    metrics_path = glow_root / "metrics.jsonl"
    assert metrics_path.exists()

    stored = json.loads(metrics_path.read_text().strip().splitlines()[-1])
    assert "signature" in stored
    assert monitor.verify_snapshot(stored)
    assert stored["windows"]["1h"]["total_events"] >= 1
    assert snapshot["signature"] == stored["signature"]


def test_query_filters_return_expected_results(monitor_factory) -> None:
    factory, _, _ = monitor_factory
    monitor = factory()
    pulse_bus.publish(_build_event("warning", priority="warning", source="NetworkDaemon"))
    pulse_bus.publish(_build_event("warning", priority="warning", source="NetworkDaemon"))
    pulse_bus.publish(_build_event("warning", priority="warning", source="StorageDaemon"))
    pulse_bus.publish(_build_event("info", priority="info", source="NetworkDaemon"))
    monitor.persist_snapshot()

    result = monitor.query("last 24h", {"priority": "warning", "source_daemon": "NetworkDaemon"})
    summary = result["summary"]
    assert summary["total_events"] == 2
    assert summary["priority"] == {"warning": 2}
    assert result["verified_snapshots"]


def test_monitor_summary_pulse_emitted_after_snapshot(monitor_factory) -> None:
    factory, _, _ = monitor_factory
    monitor = factory()

    summaries: list[dict] = []

    def capture_summary(event: dict) -> None:
        if event.get("event_type") == "monitor_summary":
            summaries.append(event)

    subscription = pulse_bus.subscribe(capture_summary)
    try:
        pulse_bus.publish(_build_event("info", priority="info", source="NetworkDaemon"))
        monitor.persist_snapshot()
    finally:
        subscription.unsubscribe()

    assert summaries, "monitor_summary pulse not observed"
    payload = summaries[-1]["payload"]
    assert "overall" in payload and "windows" in payload
