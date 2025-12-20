import pytest

from sentientos.runtime.load_homeostasis import (
    LoadHomeostasisController,
    LoadMetricSample,
    PriorityRoutingGraph,
    RoutingSubsystem,
)
from sentientos.pressure_engagement import ConstraintEngagementEngine


def build_controller() -> LoadHomeostasisController:
    graph = PriorityRoutingGraph(
        [
            RoutingSubsystem("nervous-system", "core", minimum_bandwidth=0.45),
            RoutingSubsystem("logging", "review", minimum_bandwidth=0.3),
            RoutingSubsystem("explanation", "review", minimum_bandwidth=0.3),
            RoutingSubsystem("analytics", "support", alternates=("analytics-deferred",), minimum_bandwidth=0.2),
            RoutingSubsystem("notifications", "aux", alternates=("notifications-batch",), minimum_bandwidth=0.15),
        ]
    )
    engine = ConstraintEngagementEngine(chronic_threshold=1.1, blockage_threshold=3)
    return LoadHomeostasisController(
        engagement_engine=engine,
        routing_graph=graph,
        baselines={
            "request_rate": 120.0,
            "backlog_depth": 30.0,
            "resource_contention": 0.4,
            "latency_ms": 260.0,
        },
    )


def test_graceful_degradation_under_load():
    controller = build_controller()
    sample = LoadMetricSample(
        request_rate=420.0,
        backlog_depth=180,
        resource_contention=0.92,
        latency_ms=860.0,
        environmental_notes={"source": "synthetic"},
    )

    result = controller.handle_load(sample)
    routing = result["routing"]
    explanation = result["explanation"]

    assert routing["core_preserved"] is True
    assert routing["rerouted_paths"]
    assert "analytics" in routing["throttled_inputs"]
    assert routing["allocations"]["nervous-system"] >= 0.45
    assert explanation["pressure"]["causal_graph"]["nodes"]


def test_deterministic_rerouting_plan_is_explainable():
    controller_one = build_controller()
    controller_two = build_controller()
    sample = LoadMetricSample(
        request_rate=240.0,
        backlog_depth=90,
        resource_contention=0.65,
        latency_ms=540.0,
    )

    result_one = controller_one.handle_load(sample)
    result_two = controller_two.handle_load(sample)

    assert result_one["routing"]["rerouted_paths"] == result_two["routing"]["rerouted_paths"]
    assert result_one["routing"]["throttled_inputs"] == result_two["routing"]["throttled_inputs"]
    assert result_one["explanation"]["pressure"]["status"] in {"transient", "chronic", "resolved"}


def test_recovery_reduces_rerouting_pressure():
    controller = build_controller()
    saturated = LoadMetricSample(
        request_rate=500.0,
        backlog_depth=200,
        resource_contention=1.2,
        latency_ms=980.0,
    )
    controller.handle_load(saturated)

    recovered = LoadMetricSample(
        request_rate=110.0,
        backlog_depth=20,
        resource_contention=0.25,
        latency_ms=190.0,
    )
    result = controller.handle_load(recovered)

    assert result["pressure_score"] < 0.2
    assert not result["routing"]["rerouted_paths"]
    assert result["routing"]["core_preserved"] is True


def test_posture_change_does_not_leak_authority():
    controller = build_controller()
    sample = LoadMetricSample(
        request_rate=280.0,
        backlog_depth=120,
        resource_contention=0.7,
        latency_ms=600.0,
    )
    result = controller.handle_load(sample)

    assert result["routing"]["authority_leakage"] is False
    assert result["routing"]["allocations"]["logging"] >= 0.3
    assert result["explanation"]["routing"]["reason"] == "pressure-driven reroute"
