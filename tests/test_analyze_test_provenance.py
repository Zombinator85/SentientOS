from __future__ import annotations

from scripts.analyze_test_provenance import Thresholds, analyze


def _run(*, skip_rate: float, xfail_rate: float, executed: int, passed: int, intent: str = "default", budget_allow: bool = False) -> dict[str, object]:
    return {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "run_intent": intent,
        "skip_rate": skip_rate,
        "xfail_rate": xfail_rate,
        "tests_executed": executed,
        "tests_passed": passed,
        "budget_allow_violation": budget_allow,
    }


def test_analyze_no_alert_on_stable_runs() -> None:
    runs = [_run(skip_rate=0.05, xfail_rate=0.02, executed=100, passed=98) for _ in range(8)]

    report = analyze(
        runs,
        Thresholds(
            window_size=4,
            skip_delta=0.15,
            xfail_delta=0.10,
            executed_drop=0.50,
            passed_drop=0.50,
            exceptional_cluster=3,
        ),
    )

    assert report["avoidance_alert"] is False
    assert report["avoidance_reasons"] == []


def test_analyze_alert_on_spikes_and_override() -> None:
    prior = [_run(skip_rate=0.02, xfail_rate=0.01, executed=200, passed=190) for _ in range(4)]
    current = [
        _run(skip_rate=0.25, xfail_rate=0.15, executed=80, passed=70, intent="exceptional", budget_allow=True),
        _run(skip_rate=0.24, xfail_rate=0.16, executed=80, passed=69, intent="exceptional"),
        _run(skip_rate=0.26, xfail_rate=0.14, executed=80, passed=71, intent="exceptional"),
        _run(skip_rate=0.23, xfail_rate=0.15, executed=80, passed=68),
    ]

    report = analyze(
        prior + current,
        Thresholds(
            window_size=4,
            skip_delta=0.15,
            xfail_delta=0.10,
            executed_drop=0.50,
            passed_drop=0.50,
            exceptional_cluster=3,
        ),
    )

    assert report["avoidance_alert"] is True
    assert "skip_rate_spike" in report["avoidance_reasons"]
    assert "xfail_rate_spike" in report["avoidance_reasons"]
    assert "tests_executed_collapse" in report["avoidance_reasons"]
    assert "budget_allow_violation_seen" in report["avoidance_reasons"]
    assert report["metrics"]["exceptional_count"] == 3
