from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex.proof_budget_governor import (
    GovernorConfig,
    PressureState,
    build_governor_event,
    decide_budget,
    save_pressure_state,
    update_pressure_state,
)
from scripts.verify_pressure_state_chain import verify_pressure_state_chain


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


def _next_state(prior: PressureState, *, status: str = "selected") -> PressureState:
    decision = decide_budget(config=_config(), pressure_state=prior, run_context={"pipeline": "genesis"})
    return update_pressure_state(
        prior=prior,
        decision=decision,
        router_telemetry={"escalated": False, "stage_b_evaluations": 1},
        router_status=status,
        run_context={"pipeline": "genesis", "capability": "vision", "router_attempt": 1},
        config=_config(),
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


def test_pressure_state_chain_verifies_for_sequence(tmp_path: Path) -> None:
    state_dir = tmp_path / "pressure_state"
    state = PressureState(recent_runs=[])
    for _ in range(3):
        state = _next_state(state)
        write_result = save_pressure_state(state, path=state_dir)
        assert write_result.state_update_skipped is False

    result = verify_pressure_state_chain(state_dir)
    assert result["integrity_ok"] is True
    assert result["snapshot_count"] == 3


def test_pressure_state_chain_detects_mutation(tmp_path: Path) -> None:
    state_dir = tmp_path / "pressure_state"
    state = PressureState(recent_runs=[])
    for _ in range(2):
        state = _next_state(state)
        save_pressure_state(state, path=state_dir)

    latest_snapshot = sorted((state_dir / "snapshots").glob("*.json"))[-1]
    payload = json.loads(latest_snapshot.read_text(encoding="utf-8"))
    payload["state"]["consecutive_no_admissible"] = 999
    latest_snapshot.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")

    result = verify_pressure_state_chain(state_dir)
    assert result["integrity_ok"] is False
    assert any("state_hash mismatch" in issue for issue in result["issues"])


def test_pressure_state_chain_detects_missing_middle_snapshot(tmp_path: Path) -> None:
    state_dir = tmp_path / "pressure_state"
    state = PressureState(recent_runs=[])
    for _ in range(3):
        state = _next_state(state)
        save_pressure_state(state, path=state_dir)

    snapshots = sorted((state_dir / "snapshots").glob("*.json"))
    snapshots[1].unlink()

    result = verify_pressure_state_chain(state_dir)
    assert result["integrity_ok"] is False
    assert any("prev_state_hash mismatch" in issue for issue in result["issues"])


def test_lock_contention_skips_state_update_without_crash(tmp_path: Path) -> None:
    fcntl = pytest.importorskip("fcntl")
    state_dir = tmp_path / "pressure_state"
    lock_path = state_dir / ".lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = PressureState(recent_runs=[])
        write_result = save_pressure_state(state, path=state_dir)

    assert write_result.state_update_skipped is True
    assert write_result.pressure_state_new_hash is None

    decision = decide_budget(config=_config(), pressure_state=state, run_context={"pipeline": "genesis"})
    governor_event = build_governor_event(
        decision=decision,
        config=_config(),
        run_context={"pipeline": "genesis", "capability": "vision", "router_attempt": 1},
        router_telemetry={"escalated": False},
        pressure_state_write=write_result,
    )
    assert governor_event["governor"]["state_update_skipped"] is True
