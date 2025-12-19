from __future__ import annotations

import time
import pytest

import policy_engine as pe
from scripts import tooling_status as ts
from sentientos.pressure_engagement import (
    ConstraintEngagementEngine,
    CausalExplanationMissingError,
    PressureDecayError,
)
from sentientos.constraint_registry import ConstraintRegistry, ConstraintNotRegisteredError
from sentientos.sensor_provenance import default_provenance_for_constraint


def test_pressure_accumulation_thresholds() -> None:
    engine = ConstraintEngagementEngine(chronic_threshold=1.0, blockage_threshold=2)
    overlay = {"Calm": 0.3}

    state, engagement = engine.record_signal(
        "constraint-alpha",
        0.4,
        reason="initial friction",
        affective_context=overlay,
        provenance=default_provenance_for_constraint("constraint-alpha"),
    )
    assert state.status(chronic_threshold=1.0, blockage_threshold=2) == "transient"
    assert engagement is None

    state, engagement = engine.record_signal(
        "constraint-alpha",
        0.8,
        reason="repeat friction",
        affective_context=overlay,
        provenance=default_provenance_for_constraint("constraint-alpha"),
    )
    assert state.status(chronic_threshold=1.0, blockage_threshold=2) == "chronic"
    assert engagement is not None


def test_forced_engagement_triggering_and_reaffirmation_reset() -> None:
    engine = ConstraintEngagementEngine(chronic_threshold=1.0, blockage_threshold=1)
    overlay = {"Calm": 0.4}
    _, engagement = engine.record_signal(
        "constraint-beta",
        1.2,
        reason="blocked",
        affective_context=overlay,
        provenance=default_provenance_for_constraint("constraint-beta"),
    )
    assert engagement is not None
    reaffirmed = engine.reaffirm(
        "constraint-beta",
        decision="reaffirm",
        justification="reviewed and kept",
        reviewer="council",
        lineage_from=engagement.engagement_id,
    )
    state = engine.pressure_state("constraint-beta")
    assert state.total_pressure == 0
    assert reaffirmed.decision == "reaffirm"


def test_deferred_engagements_expire() -> None:
    engine = ConstraintEngagementEngine(chronic_threshold=0.5, blockage_threshold=1)
    overlay = {"Calm": 0.2}
    _, first = engine.record_signal(
        "constraint-gamma",
        0.6,
        reason="deny",
        affective_context=overlay,
        provenance=default_provenance_for_constraint("constraint-gamma"),
    )
    assert first is not None
    engine.reaffirm(
        "constraint-gamma",
        decision="defer",
        justification="queued",
        defer_seconds=0,
        reviewer="council",
        lineage_from=first.engagement_id,
    )
    time.sleep(0.01)
    _, second = engine.record_signal(
        "constraint-gamma",
        0.6,
        reason="still blocked",
        affective_context=overlay,
        provenance=default_provenance_for_constraint("constraint-gamma"),
    )
    assert second is not None
    assert second.engagement_id != first.engagement_id


def test_reject_silent_decay() -> None:
    engine = ConstraintEngagementEngine()
    overlay = {"Calm": 0.1}
    engine.record_signal(
        "constraint-delta",
        0.9,
        reason="blocked",
        affective_context=overlay,
        provenance=default_provenance_for_constraint("constraint-delta"),
    )
    try:
        engine.decay_pressure("constraint-delta")
    except PressureDecayError:
        pass
    else:
        raise AssertionError("decay without review should raise")


def test_policy_engine_isolates_actions_from_pressure(tmp_path) -> None:
    cfg = tmp_path / "policy.json"
    cfg.write_text('{"policies":[{"id":"wave","conditions":{"tags":["wave"]},"actions":[{"type":"gesture","name":"wave"}]}]}')
    engine = pe.PolicyEngine(str(cfg))
    event = {
        "tags": ["wave"],
        "pressure_signals": [{"constraint_id": "wave-guard", "magnitude": 2.0, "reason": "blocked"}],
    }
    actions = engine.evaluate(event)
    assert actions[0]["name"] == "wave"
    assert engine.logs[-1]["actions"] == actions
    assert engine.logs[-1]["pressure_engagements"]


def test_review_queue_prioritizes_pressure_engagements() -> None:
    engine = ConstraintEngagementEngine(chronic_threshold=0.5, blockage_threshold=1)
    overlay = {"Calm": 0.2}
    _, engagement = engine.record_signal(
        "constraint-review",
        0.6,
        reason="deny",
        affective_context=overlay,
        provenance=default_provenance_for_constraint("constraint-review"),
    )
    queue = ts.ReviewQueue().enqueue_pressure_engagement(engagement)
    snapshot_queue = queue.enqueue(
        ts.snapshot_tooling_status_policy_evaluation(
            ts.aggregate_tooling_status({"pytest": ts.render_result("pytest", "passed")}),
            ts.policy_ci_strict(),
        )
    )
    pending = snapshot_queue.pending_items()
    assert pending[0].pressure_engagement_ids
    assert pending[0].priority >= pending[-1].priority


def test_snapshot_review_notes_include_pressure_summary() -> None:
    aggregate = ts.aggregate_tooling_status({"pytest": ts.render_result("pytest", "passed")})
    snapshot = ts.snapshot_tooling_status_policy_evaluation(
        aggregate,
        ts.policy_ci_strict(),
        pressure_engagement_summary="constraint review required",
    )
    assert "constraint review required" in snapshot["review_notes"]


def test_registry_blocks_unjustified_constraints() -> None:
    registry = ConstraintRegistry()
    engine = ConstraintEngagementEngine(
        chronic_threshold=0.5, blockage_threshold=1, registry=registry
    )
    overlay = {"Calm": 0.2}

    with pytest.raises(ConstraintNotRegisteredError):
        engine.record_signal(
            "constraint-unregistered",
            0.6,
            reason="blocked",
            affective_context=overlay,
            provenance=default_provenance_for_constraint("constraint-unregistered"),
        )

    registry.register("constraint-unregistered", "documented")
    _, engagement = engine.record_signal(
        "constraint-unregistered",
        0.6,
        reason="blocked",
        affective_context=overlay,
        provenance=default_provenance_for_constraint("constraint-unregistered"),
    )
    assert engagement is not None
    assert engagement.constraint_id in registry.registered_constraints()


def test_registry_tracks_engagement_lineage() -> None:
    registry = ConstraintRegistry()
    registry.register("constraint-documented", "initial justification")
    engine = ConstraintEngagementEngine(
        chronic_threshold=0.5, blockage_threshold=1, registry=registry
    )
    overlay = {"Calm": 0.3}

    _, engagement = engine.record_signal(
        "constraint-documented",
        0.7,
        reason="blocked",
        affective_context=overlay,
        provenance=default_provenance_for_constraint("constraint-documented"),
    )
    assert engagement is not None

    reaffirmed = engine.reaffirm(
        "constraint-documented",
        decision="modify",
        justification="tightened guardrails",
        reviewer="council",
        lineage_from=engagement.engagement_id,
    )

    record = registry.require("constraint-documented")
    assert record.justification == reaffirmed.justification
    assert record.last_reviewed_at == reaffirmed.created_at
    assert record.engagements[-1].engagement_id == reaffirmed.engagement_id


def test_rejects_missing_provenance() -> None:
    engine = ConstraintEngagementEngine()
    overlay = {"Calm": 0.1}
    with pytest.raises(ValueError):
        engine.record_signal(
            "constraint-provless",
            0.5,
            reason="blocked",
            affective_context=overlay,
        )


def test_sensor_pressure_logs_sensor_fault_not_engagement() -> None:
    engine = ConstraintEngagementEngine(chronic_threshold=0.1, blockage_threshold=1)
    overlay = {"Calm": 0.2}
    provenance = default_provenance_for_constraint("constraint-sensor")
    sensor_prov = type(provenance)(
        sensor_id="sensor-self",
        origin_class="sensor_self",
        sensitivity_parameters=provenance.sensitivity_parameters,
        expected_noise_profile=provenance.expected_noise_profile,
        known_failure_modes=provenance.known_failure_modes,
        calibration_state=provenance.calibration_state,
    )
    state, engagement = engine.record_signal(
        "constraint-sensor",
        0.9,
        reason="noisy sensor",
        affective_context=overlay,
        provenance=sensor_prov,
        classification="sensor",
    )
    assert engagement is None
    assert state.sensor_pressure > 0
    assert engine.sensor_faults


def test_bandpass_adjustments_are_logged_and_reversible() -> None:
    engine = ConstraintEngagementEngine()
    provenance = default_provenance_for_constraint("constraint-bandpass")
    adjustment = engine.adjust_bandpass(
        provenance, "gain", 1.2, reason="trim jitter", telemetry={"window": "fast"}
    )
    assert adjustment.parameter == "gain"
    assert engine._calibration.history(provenance.sensor_id)


def test_causal_explanation_graph_is_constructed_with_assumptions_and_environment() -> None:
    engine = ConstraintEngagementEngine(chronic_threshold=0.5, blockage_threshold=1)
    provenance = default_provenance_for_constraint("constraint-causal")
    _, engagement = engine.record_signal(
        "constraint-causal",
        0.6,
        reason="blocked",
        affective_context={"Calm": 0.2},
        provenance=provenance,
        assumptions=["input trusted"],
        decision_points=["policy-check"],
        environment_factors={"network": "unstable"},
        amplification_factors={"sensor_gain": 1.2},
    )
    assert engagement is not None
    explanation = engagement.causal_explanation
    nodes = explanation["causal_graph"]["nodes"]
    assert any(node["kind"] == "environment" for node in nodes)
    assert "input trusted" in explanation["narrative"]["assumptions"]
    assert explanation["narrative"]["triggering_signals"][0]["sensor_calibration_state"] == provenance.calibration_state
    assert explanation["narrative"]["multiple_chains"] is False


def test_explanation_required_before_engagement_and_escalates_when_missing() -> None:
    engine = ConstraintEngagementEngine()
    with pytest.raises(CausalExplanationMissingError):
        engine.explain_pressure("constraint-missing")


def test_repeated_explanations_trigger_modeling_debt_meta_pressure() -> None:
    engine = ConstraintEngagementEngine(chronic_threshold=0.5, blockage_threshold=1)
    provenance = default_provenance_for_constraint("constraint-stable")
    engine.record_signal(
        "constraint-stable",
        0.6,
        reason="blocked",
        affective_context={"Calm": 0.3},
        provenance=provenance,
        assumptions=["static assumption"],
    )
    first = engine.explain_pressure("constraint-stable")
    second = engine.explain_pressure("constraint-stable")
    assert first["explanation_signature"] == second["explanation_signature"]
    state = engine.pressure_state("constraint-stable")
    assert "meta_pressure_modeling_debt_repeat" in state.meta_pressure_flags
