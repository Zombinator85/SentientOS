from __future__ import annotations

from codex.proof_budget_governor import (
    GovernorConfig,
    PressureState,
    decide_budget,
)


def _config() -> GovernorConfig:
    return GovernorConfig(
        configured_k=5,
        configured_m=3,
        max_k=9,
        escalation_enabled=True,
        mode="auto",
        admissible_collapse_runs=3,
        min_m=1,
        diagnostics_k=4,
        pressure_window=6,
        proof_burn_spike_runs=2,
        escalation_cluster_runs=2,
    )


def test_governor_decision_is_deterministic_for_fixed_inputs() -> None:
    state = PressureState(
        consecutive_no_admissible=1,
        recent_runs=[
            {"proof_burn_spike": True, "escalated": False},
            {"proof_burn_spike": True, "escalated": True},
        ],
    )
    context = {"pipeline": "specamend", "spec_id": "spec-a", "router_attempt": 1}
    one = decide_budget(config=_config(), pressure_state=state, run_context=context)
    two = decide_budget(config=_config(), pressure_state=state, run_context=context)
    assert one == two


def test_proof_burn_spike_reduces_m_and_disables_escalation() -> None:
    state = PressureState(
        consecutive_no_admissible=0,
        recent_runs=[
            {"proof_burn_spike": True, "escalated": False},
            {"proof_burn_spike": True, "escalated": False},
        ],
    )
    decision = decide_budget(config=_config(), pressure_state=state, run_context={"pipeline": "genesis"})
    assert decision.mode == "constrained"
    assert decision.m_effective == 2
    assert decision.allow_escalation is False
    assert "proof_burn_spike" in decision.decision_reasons


def test_admissible_collapse_forces_diagnostics_only_after_threshold() -> None:
    state = PressureState(consecutive_no_admissible=3, recent_runs=[])
    decision = decide_budget(config=_config(), pressure_state=state, run_context={"pipeline": "genesis"})
    assert decision.mode == "diagnostics_only"
    assert decision.m_effective == 0
    assert decision.allow_escalation is False
    assert "admissible_collapse" in decision.decision_reasons
