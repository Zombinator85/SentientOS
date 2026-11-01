from __future__ import annotations

import math

import pytest

from sentientos.daemons.integrity_daemon import IntegrityDaemon
from sentientos.daemons.monitoring_daemon import _query_http_port

pytestmark = pytest.mark.no_legacy_skip


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, 0), ("8123", 8123), (True, 0), (object(), 0), ("invalid", 0), (math.inf, 0)],
)
def test_query_http_port_accepts_only_parseable_numeric_values(value: object, expected: int) -> None:
    assert _query_http_port(value) == expected


@pytest.mark.parametrize("risk", ["invalid", None, True, math.nan, math.inf])
def test_invalid_hungry_eyes_risk_withholds_dual_control(risk: object) -> None:
    class Observer:
        mode = "observe"

        def assess(self, _event: object) -> dict[str, object]:
            return {"risk": risk, "threshold": 0.6}

    event: dict[str, object] = {"proof_report": {"valid": True}}
    daemon = IntegrityDaemon(hungry_eyes=Observer(), hungry_threshold=0.6)
    try:
        daemon._integrate_hungry_eyes(event)
        dual_control = event["proof_report"]["dual_control"]
        assert dual_control["auto_commit"] is False
        assert dual_control["hungry_eyes_risk"] == dual_control["threshold"] == 0.6
    finally:
        daemon.stop()


def test_invalid_hungry_eyes_threshold_withholds_dual_control() -> None:
    class Observer:
        mode = "observe"

        def assess(self, _event: object) -> dict[str, object]:
            return {"risk": 0.0, "threshold": "invalid"}

    event: dict[str, object] = {"proof_report": {"valid": True}}
    daemon = IntegrityDaemon(hungry_eyes=Observer(), hungry_threshold=0.6)
    try:
        daemon._integrate_hungry_eyes(event)
        dual_control = event["proof_report"]["dual_control"]
        assert dual_control["auto_commit"] is False
        assert dual_control["hungry_eyes_risk"] == dual_control["threshold"] == 0.6
    finally:
        daemon.stop()
