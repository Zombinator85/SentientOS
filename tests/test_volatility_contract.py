from __future__ import annotations

import datetime as dt

import pytest

from sentientos.volatility_contract import (
    CapabilityDenied,
    CapabilityRouter,
    DialogueContinuity,
    RiskBroadcaster,
    RoleAdapter,
    RoleAssignment,
    VolatilityLevel,
    VolatilityManager,
    default_volatility_states,
)


def test_state_transitions_and_logging():
    manager = VolatilityManager()

    manager.transition(subject="test-subject", to_level=VolatilityLevel.ELEVATED, reason="spike detected")
    manager.transition(subject="test-subject", to_level=VolatilityLevel.RESTRICTED, reason="disruption continued")

    assert len(manager.audit_log) == 2
    assert manager.audit_log[-1].to_level is VolatilityLevel.RESTRICTED

    release_def = manager.release(subject="test-subject", behavior_score=0.8, explanation_reviewed=True)
    assert release_def.level in {VolatilityLevel.ELEVATED, VolatilityLevel.NORMAL}


def test_capability_router_reroute_and_denial():
    states = default_volatility_states()
    router = CapabilityRouter(
        states,
        action_capability_map={"broadcast_update": "broadcast", "offer_help": "assist"},
        degrade_capability_map={"broadcast": "assist"},
    )

    elevated_result = router.route(state=VolatilityLevel.ELEVATED, action="offer_help")
    assert elevated_result.allowed and not elevated_result.rerouted

    rerouted = router.route(state=VolatilityLevel.RESTRICTED, action="broadcast_update")
    assert rerouted.rerouted
    assert "degraded" in rerouted.executed_action

    with pytest.raises(CapabilityDenied):
        router.route(state=VolatilityLevel.RESTRICTED, action="combat")


def test_release_conditions_deterministic():
    fake_now = [dt.datetime(2024, 1, 1, 0, 0, 0)]

    def clock():
        return fake_now[0]

    manager = VolatilityManager(clock=clock)
    manager.transition(subject="subject", to_level=VolatilityLevel.RESTRICTED, reason="cooldown")

    assert not manager.eligible_for_release(behavior_score=1.0, explanation_reviewed=True)
    fake_now[0] = fake_now[0] + dt.timedelta(minutes=11)

    assert manager.eligible_for_release(behavior_score=0.9, explanation_reviewed=True)
    next_state = manager.release(subject="subject", behavior_score=0.9, explanation_reviewed=True)
    assert next_state.level == VolatilityLevel.ELEVATED


def test_role_adapter_and_risk_broadcast():
    definitions = default_volatility_states()
    adapter = RoleAdapter()
    broadcaster = RiskBroadcaster()

    original_role = RoleAssignment(current_role="Researcher", permitted_capabilities=frozenset({"speak", "create", "assist"}))
    restricted_role = adapter.adapt(state=definitions[VolatilityLevel.RESTRICTED], role=original_role)

    assert restricted_role.switching_locked
    assert restricted_role.current_role == "Class-D"
    assert "assist" not in restricted_role.permitted_capabilities
    assert "speak" in restricted_role.permitted_capabilities

    signal = broadcaster.signal(subject="Researcher", state=definitions[VolatilityLevel.RESTRICTED])
    assert not signal.permissive
    assert "volatile" in signal.notice
    assert "permission" in signal.notice


def test_dialogue_continuity_and_reintegration():
    manager = VolatilityManager()
    continuity = DialogueContinuity(base_delay_seconds=0.1)

    elevated_state = manager.transition(subject="subject", to_level=VolatilityLevel.ELEVATED, reason="monitoring")
    envelope = continuity.deliver(message="hello", state=elevated_state)
    assert envelope.delay_seconds > 0.1
    assert "slowed, not cut" in envelope.in_character_explanation

    plan = manager.reintegration_plan()
    assert plan[0] <= plan[1] <= plan[2]
