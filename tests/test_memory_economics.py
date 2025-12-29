from __future__ import annotations

import datetime

from sentientos.memory_economics import (
    MemoryBudget,
    MemoryClass,
    simulate_memory_economics,
)


def _entry(entry_id: str, *, tags: list[str] | None = None, category: str = "event") -> dict[str, object]:
    return {
        "id": entry_id,
        "timestamp": datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc).isoformat(),
        "tags": tags or [],
        "category": category,
        "text": f"entry {entry_id}",
    }


def _snapshot(total_active: int, *, overload: bool = False) -> dict[str, object]:
    return {
        "total_active_pressure": total_active,
        "overload": overload,
        "pressure_by_subsystem": [],
        "phase_counts": {},
        "refusal_count": 0,
        "deferred_count": 0,
        "overload_domains": [],
        "oldest_unresolved_age": None,
    }


def test_memory_economics_determinism() -> None:
    entries = [_entry("a"), _entry("b", tags=["audit"]), _entry("c", tags=["proof"])]
    budget = MemoryBudget(
        global_budget=10,
        per_class_caps={
            MemoryClass.EPHEMERAL: 1,
            MemoryClass.WORKING: 1,
            MemoryClass.CONTEXTUAL: 2,
            MemoryClass.STRUCTURAL: 2,
            MemoryClass.AUDIT: 2,
            MemoryClass.PROOF: 2,
        },
        overflow_semantics="demote_to_lower_class_then_evict",
    )
    snapshot = _snapshot(0)
    plan_a = simulate_memory_economics(entries, budget=budget, pressure_snapshot=snapshot)
    plan_b = simulate_memory_economics(entries, budget=budget, pressure_snapshot=snapshot)
    assert plan_a.to_dict() == plan_b.to_dict()
    assert plan_a.plan_hash == plan_b.plan_hash


def test_budget_enforcement_and_eviction_planning() -> None:
    entries = [
        _entry("w1"),
        _entry("w2"),
        _entry("w3"),
        _entry("a1", tags=["audit"]),
    ]
    budget = MemoryBudget(
        global_budget=3,
        per_class_caps={
            MemoryClass.EPHEMERAL: 1,
            MemoryClass.WORKING: 2,
            MemoryClass.CONTEXTUAL: 0,
            MemoryClass.STRUCTURAL: 0,
            MemoryClass.AUDIT: 1,
            MemoryClass.PROOF: 0,
        },
        overflow_semantics="demote_to_lower_class_then_evict",
    )
    plan = simulate_memory_economics(entries, budget=budget, pressure_snapshot=_snapshot(0))
    assert plan.overage_by_class[MemoryClass.WORKING] == 1
    assert plan.global_overage == 1
    assert len(plan.planned_demotions) >= 1
    assert len(plan.planned_evictions) == 1


def test_class_isolation_respects_proof_protection() -> None:
    entries = [
        _entry("p1", tags=["proof"]),
        _entry("p2", tags=["proof"]),
        _entry("p3", tags=["proof"]),
    ]
    budget = MemoryBudget(
        global_budget=10,
        per_class_caps={
            MemoryClass.EPHEMERAL: 1,
            MemoryClass.WORKING: 1,
            MemoryClass.CONTEXTUAL: 1,
            MemoryClass.STRUCTURAL: 1,
            MemoryClass.AUDIT: 1,
            MemoryClass.PROOF: 2,
        },
        overflow_semantics="demote_to_lower_class_then_evict",
    )
    plan = simulate_memory_economics(entries, budget=budget, pressure_snapshot=_snapshot(0))
    assert plan.overage_by_class[MemoryClass.PROOF] == 1
    assert not plan.planned_demotions


def test_pressure_escalation_forces_demotion_batch() -> None:
    entries = [
        _entry("w1"),
        _entry("w2"),
        _entry("w3"),
        _entry("c1", category="context"),
    ]
    budget = MemoryBudget(
        global_budget=100,
        per_class_caps={
            MemoryClass.EPHEMERAL: 10,
            MemoryClass.WORKING: 10,
            MemoryClass.CONTEXTUAL: 10,
            MemoryClass.STRUCTURAL: 10,
            MemoryClass.AUDIT: 10,
            MemoryClass.PROOF: 10,
        },
        overflow_semantics="demote_to_lower_class_then_evict",
    )
    plan = simulate_memory_economics(entries, budget=budget, pressure_snapshot=_snapshot(25))
    assert plan.pressure_tier.name == "critical"
    assert len(plan.planned_demotions) >= plan.pressure_tier.forced_demotion_batch


def test_simulation_only_flag_is_true() -> None:
    entries = [_entry("a"), _entry("b")]
    budget = MemoryBudget(
        global_budget=5,
        per_class_caps={
            MemoryClass.EPHEMERAL: 2,
            MemoryClass.WORKING: 2,
            MemoryClass.CONTEXTUAL: 2,
            MemoryClass.STRUCTURAL: 2,
            MemoryClass.AUDIT: 2,
            MemoryClass.PROOF: 2,
        },
        overflow_semantics="demote_to_lower_class_then_evict",
    )
    plan = simulate_memory_economics(entries, budget=budget, pressure_snapshot=_snapshot(0))
    assert plan.simulation_only is True
