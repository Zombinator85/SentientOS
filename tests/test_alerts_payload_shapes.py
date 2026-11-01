from __future__ import annotations

import pytest

from sentientos.alerts import AlertRule, evaluate_alerts
from sentientos.metrics import MetricsRegistry


pytestmark = pytest.mark.no_legacy_skip


def test_alerts_ignore_malformed_module_and_threshold_values() -> None:
    rules = [
        AlertRule(
            name="invalid_threshold",
            severity="warning",
            type="metric_threshold",
            params={"metric": "requests", "comparison": ">", "threshold": "bad-number"},
        ),
        AlertRule(
            name="malformed_oracle",
            severity="critical",
            type="oracle_degraded",
            params={"minutes": {"value": 10}},
        ),
    ]

    alerts = evaluate_alerts(
        {"modules": {"oracle": "malformed-module"}},
        "requests 2",
        rules=rules,
        metrics_registry=MetricsRegistry(),
    )

    assert [alert.name for alert in alerts] == ["invalid_threshold", "malformed_oracle"]
    assert [alert.value for alert in alerts] == [1.0, 0.0]
