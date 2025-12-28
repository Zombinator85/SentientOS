from __future__ import annotations

from pathlib import Path

from sentientos.consciousness.cognitive_posture import (
    CognitivePosture,
    LoadNarrative,
    derive_cognitive_posture,
    derive_load_narrative,
    derive_posture_transition,
    update_posture_history,
)
from sentientos.consciousness.inner_narrator import generate_reflection
from sentientos.consciousness.integration import run_consciousness_cycle
from sentientos.consciousness.simulation_engine import SimulationEngine
from sentientos.governance import intentional_forgetting as forgetting


def _append_pressure_entry(
    log_path: Path,
    *,
    forget_tx_id: str,
    subsystem: str,
    phase: str,
) -> None:
    entry = {
        "event": "intentional_forget_pressure",
        "forget_tx_id": forget_tx_id,
        "target_type": "memory",
        "target": "hash:abc123",
        "forget_scope": "exact",
        "proof_level": "structural",
        "authority": "operator",
        "redacted_target": True,
        "defer_acknowledged": False,
        "status": "active",
        "phase": phase,
        "subsystems": [
            {
                "subsystem": subsystem,
                "decision": "refuse" if phase == "refused" else "defer",
                "reason_hash": "deadbeef",
            }
        ],
        "pressure_weight": 1.0,
    }
    entry["pressure_hash"] = forgetting._hash_payload(entry)
    forgetting._append_pressure(log_path, entry)


def test_posture_deterministic_and_read_only() -> None:
    snapshot = {"total_active_pressure": 0, "overload": False}
    snapshot_before = dict(snapshot)

    assert derive_cognitive_posture(snapshot) == CognitivePosture.STABLE
    assert derive_cognitive_posture(snapshot) == CognitivePosture.STABLE
    assert snapshot == snapshot_before


def test_posture_boundary_at_budget_limit(tmp_path: Path) -> None:
    log_path = tmp_path / "intentional_forgetting.jsonl"
    budgets = {"default": forgetting.ForgetPressureBudget(max_outstanding=1, max_duration=10, max_weight=2.0)}

    _append_pressure_entry(log_path, forget_tx_id="tx-1", subsystem="memory", phase="refused")
    snapshot = forgetting.build_forget_pressure_snapshot(log_path, budgets=budgets)
    assert snapshot["overload"] is False
    assert derive_cognitive_posture(snapshot) == CognitivePosture.TENSE

    _append_pressure_entry(log_path, forget_tx_id="tx-2", subsystem="memory", phase="deferred")
    overload_snapshot = forgetting.build_forget_pressure_snapshot(log_path, budgets=budgets)
    assert overload_snapshot["overload"] is True
    assert derive_cognitive_posture(overload_snapshot) == CognitivePosture.OVERLOADED


def test_simulation_posture_parity(tmp_path: Path) -> None:
    snapshot = {
        "total_active_pressure": 1,
        "pressure_by_subsystem": [{"subsystem": "memory", "count": 1}],
        "overload": False,
    }
    history = ["stable", "stable"]
    engine = SimulationEngine(log_path=tmp_path / "simulation.jsonl", pulse_state_path=tmp_path / "pulse.json")
    result = run_consciousness_cycle(
        {
            "pressure_snapshot": snapshot,
            "posture_history": history,
            "simulation_engine": engine,
        }
    )

    assert result["cognitive_posture"] == "tense"
    assert result["simulation_output"]["cognitive_posture"] == result["cognitive_posture"]
    assert result["posture_history"] == result["simulation_output"]["posture_history"]
    assert result["posture_transition"] == result["simulation_output"]["posture_transition"]
    assert result["cognitive_load_narrative"] == "ACCUMULATING_TENSION"
    assert result["simulation_output"]["cognitive_load_narrative"] == result["cognitive_load_narrative"]
    assert history == ["stable", "stable"]
    assert snapshot == {
        "total_active_pressure": 1,
        "pressure_by_subsystem": [{"subsystem": "memory", "count": 1}],
        "overload": False,
    }


def test_narrator_acknowledges_cognitive_posture() -> None:
    reflection, mood, focus, attention = generate_reflection(
        {"events": [], "cycle": 1},
        {},
        pressure_snapshot={
            "total_active_pressure": 1,
            "pressure_by_subsystem": [{"subsystem": "memory", "count": 1}],
            "overload": False,
        },
        cognitive_posture="tense",
    )

    assert "Cognitive posture tense" in reflection
    assert mood in {"stable", "uncertain", "curious"}
    assert focus
    assert attention


def test_narrator_reports_load_narrative_transitions() -> None:
    reflection, _, _, _ = generate_reflection(
        {"events": [], "cycle": 1},
        {},
        cognitive_posture="stable",
        posture_history=["overloaded", "stable"],
        posture_transition="OVERLOADED→STABLE",
        posture_duration=1,
        cognitive_load_narrative="RECOVERING",
    )

    assert "Load narrative recovering; transitioned to recovering" in reflection


def test_load_narrative_deterministic_and_read_only() -> None:
    history = ["stable", "tense", "tense"]
    history_before = list(history)
    transitions = derive_posture_transition(history)
    transitions_before = dict(transitions)

    assert derive_load_narrative(history, transitions) == LoadNarrative.ACCUMULATING_TENSION
    assert derive_load_narrative(history, transitions) == LoadNarrative.ACCUMULATING_TENSION
    assert history == history_before
    assert transitions == transitions_before


def test_load_narrative_sustained_vs_transient_tension() -> None:
    transient_history = ["stable", "tense", "tense"]
    sustained_history = ["stable", "tense", "tense", "tense"]

    transient_transition = derive_posture_transition(transient_history)
    sustained_transition = derive_posture_transition(sustained_history)

    assert derive_load_narrative(transient_history, transient_transition) == LoadNarrative.ACCUMULATING_TENSION
    assert derive_load_narrative(sustained_history, sustained_transition) == LoadNarrative.SUSTAINED_TENSION


def test_load_narrative_recovery_detection() -> None:
    history = ["overloaded", "stable"]
    transition = derive_posture_transition(history)

    assert derive_load_narrative(history, transition) == LoadNarrative.RECOVERING


def test_posture_history_window_and_transition() -> None:
    history = ["stable", "tense", "tense"]
    updated = update_posture_history(history, "overloaded", window=3)
    assert updated == ["tense", "tense", "overloaded"]
    assert history == ["stable", "tense", "tense"]

    transition = derive_posture_transition(updated)
    assert transition["posture_transition"] == "TENSE→OVERLOADED"
    assert transition["posture_duration"] == 1


def test_posture_duration_calculation() -> None:
    history = ["stable", "tense", "tense", "tense"]
    transition = derive_posture_transition(history)
    assert transition["current_posture"] == "tense"
    assert transition["posture_duration"] == 3
