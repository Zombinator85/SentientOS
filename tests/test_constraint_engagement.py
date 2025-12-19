from __future__ import annotations

import time

import policy_engine as pe
from scripts import tooling_status as ts
from sentientos.pressure_engagement import (
    ConstraintEngagementEngine,
    PressureDecayError,
)


def test_pressure_accumulation_thresholds() -> None:
    engine = ConstraintEngagementEngine(chronic_threshold=1.0, blockage_threshold=2)
    overlay = {"Calm": 0.3}

    state, engagement = engine.record_signal(
        "constraint-alpha", 0.4, reason="initial friction", affective_context=overlay
    )
    assert state.status(chronic_threshold=1.0, blockage_threshold=2) == "transient"
    assert engagement is None

    state, engagement = engine.record_signal(
        "constraint-alpha", 0.8, reason="repeat friction", affective_context=overlay
    )
    assert state.status(chronic_threshold=1.0, blockage_threshold=2) == "chronic"
    assert engagement is not None


def test_forced_engagement_triggering_and_reaffirmation_reset() -> None:
    engine = ConstraintEngagementEngine(chronic_threshold=1.0, blockage_threshold=1)
    overlay = {"Calm": 0.4}
    _, engagement = engine.record_signal(
        "constraint-beta", 1.2, reason="blocked", affective_context=overlay
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
    _, first = engine.record_signal("constraint-gamma", 0.6, reason="deny", affective_context=overlay)
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
        "constraint-gamma", 0.6, reason="still blocked", affective_context=overlay
    )
    assert second is not None
    assert second.engagement_id != first.engagement_id


def test_reject_silent_decay() -> None:
    engine = ConstraintEngagementEngine()
    overlay = {"Calm": 0.1}
    engine.record_signal("constraint-delta", 0.9, reason="blocked", affective_context=overlay)
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
    _, engagement = engine.record_signal("constraint-review", 0.6, reason="deny", affective_context=overlay)
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
