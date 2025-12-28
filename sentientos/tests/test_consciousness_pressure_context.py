from __future__ import annotations

from pathlib import Path

from sentientos.consciousness.integration import run_consciousness_cycle
from sentientos.consciousness.sentience_kernel import SentienceKernel
from sentientos.governance import intentional_forgetting as forgetting
from sentientos.narrative_synthesis import _build_activity_section


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


def test_pressure_snapshot_deterministic_and_read_only(tmp_path: Path) -> None:
    log_path = tmp_path / "intentional_forgetting.jsonl"
    _append_pressure_entry(log_path, forget_tx_id="tx-1", subsystem="memory", phase="refused")
    _append_pressure_entry(log_path, forget_tx_id="tx-2", subsystem="cor", phase="deferred")

    entries_before = forgetting.read_forget_log(log_path)
    snapshot_one = forgetting.build_forget_pressure_snapshot(log_path)
    snapshot_two = forgetting.build_forget_pressure_snapshot(log_path)
    entries_after = forgetting.read_forget_log(log_path)

    assert snapshot_one == snapshot_two
    assert entries_before == entries_after
    assert snapshot_one["total_active_pressure"] == 2
    assert snapshot_one["pressure_by_subsystem"] == [
        {"subsystem": "cor", "count": 1},
        {"subsystem": "memory", "count": 1},
    ]
    assert snapshot_one["oldest_unresolved_age"] is not None


def test_consciousness_cycle_includes_pressure_context() -> None:
    snapshot = {
        "total_active_pressure": 1,
        "pressure_by_subsystem": [{"subsystem": "memory", "count": 1}],
        "phase_counts": {"refused": 1},
        "refusal_count": 1,
        "deferred_count": 0,
        "overload": False,
        "overload_domains": [],
        "oldest_unresolved_age": 0,
        "snapshot_hash": "abc123",
    }
    result = run_consciousness_cycle({"pressure_snapshot": snapshot})
    assert result["pressure_snapshot"] == snapshot


def test_kernel_behavior_unchanged_without_pressure_snapshot() -> None:
    kernel = SentienceKernel()
    state = {"last_focus": None, "novelty_score": 0.1, "goal_context": {"system_load": 0.2}}

    should_generate, trigger = kernel._should_generate_goal(state, pressure_snapshot=None)
    assert should_generate is True
    assert trigger == "curiosity"


def test_kernel_reflects_overload_bias() -> None:
    kernel = SentienceKernel()
    state = {"last_focus": None, "novelty_score": 0.1, "goal_context": {"system_load": 0.2}}
    pressure_snapshot = {"overload": True, "total_active_pressure": 3}

    should_generate, trigger = kernel._should_generate_goal(state, pressure_snapshot=pressure_snapshot)
    assert should_generate is True
    assert trigger == "reflection_overload"


def test_overload_reflected_in_narrative_summary() -> None:
    activity = {
        "tasks": {"tasks": []},
        "routines": {"routines": []},
        "admissions": {"denials": []},
        "forgetting": {},
        "forgetting_pressure": {
            "count": 2,
            "scope": ["memory"],
            "overload_count": 1,
            "overload_domains": [{"subsystem": "memory", "outstanding": 2}],
        },
        "task_entries": [],
        "routine_entries": [],
        "admission_entries": [],
        "forgetting_entries": [],
    }
    section = _build_activity_section(activity)
    assert any("System under sustained tension" in line for line in section["lines"])
