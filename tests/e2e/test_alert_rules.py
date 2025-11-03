from datetime import datetime, timedelta, timezone

from sentientos.alerts import evaluate_alerts
from sentientos.metrics import MetricsRegistry


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def test_alert_rules_trigger_on_thresholds() -> None:
    registry = MetricsRegistry()
    registry.observe("sos_reflexion_latency_ms", 2500)
    registry.increment("sos_council_quorum_misses_total", 1)
    registry.increment("sos_event_signature_mismatches_total", 2)
    registry.increment("sos_admin_requests_total", 100)
    registry.increment("sos_admin_failures_total", 1)
    metrics_text = registry.export_prometheus()
    modules = {
        "memory_curator": {"status": "healthy", "backlog": 42},
        "oracle": {
            "status": "degraded",
            "last_degraded_at": _iso(datetime.now(timezone.utc) - timedelta(minutes=20)),
        },
        "hungry_eyes": {
            "status": "healthy",
            "last_retrain": _iso(datetime.now(timezone.utc) - timedelta(days=8)),
        },
    }
    status = {"modules": modules}
    alerts = evaluate_alerts(status, metrics_text, metrics_registry=registry)
    result = {alert.name: alert for alert in alerts}
    assert result["HighReflexionTimeouts"].value == 1.0
    assert result["NoQuorum"].value == 1.0
    assert result["OracleDegradedSustained"].value == 1.0
    assert result["CuratorBacklogHigh"].value == 1.0
    assert result["HungryEyesStaleModel"].value == 1.0
    assert result["EventSignatureMismatches"].value == 1.0
