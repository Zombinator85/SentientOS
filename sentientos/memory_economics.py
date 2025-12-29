from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Sequence

from sentientos.governance.intentional_forgetting import (
    DEFAULT_LOG_PATH as DEFAULT_FORGET_LOG,
    build_forget_pressure_snapshot,
)
from sentientos.introspection.spine import DEFAULT_LOG_PATH, EventType, emit_introspection_event


class MemoryClass(str, Enum):
    EPHEMERAL = "EPHEMERAL"
    WORKING = "WORKING"
    CONTEXTUAL = "CONTEXTUAL"
    STRUCTURAL = "STRUCTURAL"
    AUDIT = "AUDIT"
    PROOF = "PROOF"


@dataclass(frozen=True)
class MemoryClassPolicy:
    retention_days: int
    eviction_priority: int
    compressibility: str
    redaction_rules: tuple[str, ...]
    demotion_protected: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "retention_days": self.retention_days,
            "eviction_priority": self.eviction_priority,
            "compressibility": self.compressibility,
            "redaction_rules": list(self.redaction_rules),
            "demotion_protected": self.demotion_protected,
        }


@dataclass(frozen=True)
class MemoryBudget:
    global_budget: int
    per_class_caps: Mapping[MemoryClass, int]
    overflow_semantics: str

    def to_dict(self) -> dict[str, object]:
        return {
            "global_budget": self.global_budget,
            "per_class_caps": {key.value: value for key, value in self.per_class_caps.items()},
            "overflow_semantics": self.overflow_semantics,
        }


@dataclass(frozen=True)
class PressureTier:
    name: str
    min_active_pressure: int
    retention_cost_multiplier: float
    decay_multiplier: float
    forced_demotion_batch: int

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "min_active_pressure": self.min_active_pressure,
            "retention_cost_multiplier": self.retention_cost_multiplier,
            "decay_multiplier": self.decay_multiplier,
            "forced_demotion_batch": self.forced_demotion_batch,
        }


@dataclass(frozen=True)
class MemoryEconomicPlan:
    simulation_only: bool
    budget: MemoryBudget
    usage_by_class: Mapping[MemoryClass, int]
    overage_by_class: Mapping[MemoryClass, int]
    global_overage: int
    pressure_snapshot: Mapping[str, object]
    pressure_tier: PressureTier
    planned_demotions: tuple[dict[str, object], ...]
    planned_evictions: tuple[dict[str, object], ...]
    plan_hash: str

    def to_dict(self) -> dict[str, object]:
        return {
            "simulation_only": self.simulation_only,
            "budget": self.budget.to_dict(),
            "usage_by_class": {key.value: value for key, value in self.usage_by_class.items()},
            "overage_by_class": {key.value: value for key, value in self.overage_by_class.items()},
            "global_overage": self.global_overage,
            "pressure_snapshot": dict(self.pressure_snapshot),
            "pressure_tier": self.pressure_tier.to_dict(),
            "planned_demotions": [dict(item) for item in self.planned_demotions],
            "planned_evictions": [dict(item) for item in self.planned_evictions],
            "plan_hash": self.plan_hash,
        }


DEFAULT_CLASS_POLICIES: dict[MemoryClass, MemoryClassPolicy] = {
    MemoryClass.EPHEMERAL: MemoryClassPolicy(
        retention_days=1,
        eviction_priority=100,
        compressibility="lossy",
        redaction_rules=("secrets", "credentials", "raw_input"),
    ),
    MemoryClass.WORKING: MemoryClassPolicy(
        retention_days=7,
        eviction_priority=90,
        compressibility="summary",
        redaction_rules=("personally_identifying", "session_only"),
    ),
    MemoryClass.CONTEXTUAL: MemoryClassPolicy(
        retention_days=30,
        eviction_priority=70,
        compressibility="summary",
        redaction_rules=("session_only",),
    ),
    MemoryClass.STRUCTURAL: MemoryClassPolicy(
        retention_days=180,
        eviction_priority=50,
        compressibility="lossless",
        redaction_rules=("policy_sensitive",),
    ),
    MemoryClass.AUDIT: MemoryClassPolicy(
        retention_days=365,
        eviction_priority=20,
        compressibility="lossless",
        redaction_rules=("audit_salt", "privacy_lane"),
    ),
    MemoryClass.PROOF: MemoryClassPolicy(
        retention_days=3650,
        eviction_priority=10,
        compressibility="immutable",
        redaction_rules=("sealed",),
        demotion_protected=True,
    ),
}

DEFAULT_BUDGET = MemoryBudget(
    global_budget=1000,
    per_class_caps={
        MemoryClass.EPHEMERAL: 100,
        MemoryClass.WORKING: 150,
        MemoryClass.CONTEXTUAL: 300,
        MemoryClass.STRUCTURAL: 200,
        MemoryClass.AUDIT: 150,
        MemoryClass.PROOF: 100,
    },
    overflow_semantics="demote_to_lower_class_then_evict",
)

PRESSURE_TIERS: tuple[PressureTier, ...] = (
    PressureTier(
        name="quiet",
        min_active_pressure=0,
        retention_cost_multiplier=1.0,
        decay_multiplier=1.0,
        forced_demotion_batch=0,
    ),
    PressureTier(
        name="elevated",
        min_active_pressure=5,
        retention_cost_multiplier=1.25,
        decay_multiplier=1.1,
        forced_demotion_batch=1,
    ),
    PressureTier(
        name="high",
        min_active_pressure=10,
        retention_cost_multiplier=1.5,
        decay_multiplier=1.25,
        forced_demotion_batch=2,
    ),
    PressureTier(
        name="critical",
        min_active_pressure=20,
        retention_cost_multiplier=2.0,
        decay_multiplier=1.5,
        forced_demotion_batch=3,
    ),
)

_DEMOTION_ORDER = (
    MemoryClass.PROOF,
    MemoryClass.AUDIT,
    MemoryClass.STRUCTURAL,
    MemoryClass.CONTEXTUAL,
    MemoryClass.WORKING,
    MemoryClass.EPHEMERAL,
)


def classify_memory(entry: Mapping[str, object]) -> MemoryClass:
    tags = {str(tag).lower() for tag in entry.get("tags", []) if tag}
    category = str(entry.get("category", "")).lower()
    source = str(entry.get("source", "")).lower()
    if tags.intersection({"proof", "attestation", "evidence"}) or "proof" in source:
        return MemoryClass.PROOF
    if tags.intersection({"audit", "audit_log", "audit_trail"}) or "audit" in source:
        return MemoryClass.AUDIT
    if tags.intersection({"structural", "policy", "doctrine", "invariant", "schema"}) or category in {
        "goal",
        "insight",
    }:
        return MemoryClass.STRUCTURAL
    if tags.intersection({"working", "scratch", "scratchpad"}) or category == "event":
        return MemoryClass.WORKING
    if tags.intersection({"ephemeral", "transient", "temp"}) or category == "dream":
        return MemoryClass.EPHEMERAL
    return MemoryClass.CONTEXTUAL


def select_pressure_tier(snapshot: Mapping[str, object]) -> PressureTier:
    total_active = int(snapshot.get("total_active_pressure", 0) or 0)
    overload = bool(snapshot.get("overload"))
    tiers = sorted(PRESSURE_TIERS, key=lambda tier: tier.min_active_pressure, reverse=True)
    for tier in tiers:
        if total_active >= tier.min_active_pressure:
            chosen = tier
            break
    else:
        chosen = PRESSURE_TIERS[0]
    if overload and chosen.name != "critical":
        for tier in tiers:
            if tier.name == "critical":
                return tier
    return chosen


def simulate_memory_economics(
    entries: Sequence[Mapping[str, object]],
    *,
    budget: MemoryBudget | None = None,
    class_policies: Mapping[MemoryClass, MemoryClassPolicy] | None = None,
    pressure_snapshot: Mapping[str, object] | None = None,
    pressure_log_path: str | None = None,
    emit_introspection: bool = True,
    introspection_path: str | None = None,
) -> MemoryEconomicPlan:
    policy_map = dict(class_policies or DEFAULT_CLASS_POLICIES)
    budget = budget or DEFAULT_BUDGET
    if pressure_snapshot is None:
        log_path = pressure_log_path or str(DEFAULT_FORGET_LOG)
        pressure_snapshot = build_forget_pressure_snapshot(log_path)
    pressure_snapshot = dict(pressure_snapshot)
    tier = select_pressure_tier(pressure_snapshot)
    entries_by_class: dict[MemoryClass, list[Mapping[str, object]]] = {
        cls: [] for cls in MemoryClass
    }
    for entry in entries:
        entries_by_class[classify_memory(entry)].append(entry)
    usage_by_class = {cls: len(items) for cls, items in entries_by_class.items()}
    overage_by_class = {
        cls: max(0, usage_by_class.get(cls, 0) - budget.per_class_caps.get(cls, 0))
        for cls in MemoryClass
    }
    total_usage = sum(usage_by_class.values())
    global_overage = max(0, total_usage - budget.global_budget)

    planned_demotions: list[dict[str, object]] = []
    planned_evictions: list[dict[str, object]] = []

    for cls in _DEMOTION_ORDER:
        if overage_by_class.get(cls, 0) <= 0:
            continue
        candidates = _ordered_candidates(entries_by_class.get(cls, []))
        demote_count = overage_by_class.get(cls, 0)
        planned_demotions.extend(
            _plan_moves(candidates, cls, policy_map, demote_count, reason="class_budget")
        )

    if tier.forced_demotion_batch > 0:
        for cls in _DEMOTION_ORDER:
            if cls == MemoryClass.PROOF:
                continue
            candidates = _ordered_candidates(entries_by_class.get(cls, []))
            planned_demotions.extend(
                _plan_moves(
                    candidates,
                    cls,
                    policy_map,
                    tier.forced_demotion_batch,
                    reason="pressure_escalation",
                )
            )

    if global_overage > 0:
        eviction_candidates = _ordered_global_candidates(entries_by_class)
        planned_evictions.extend(
            _plan_evictions(eviction_candidates, global_overage, reason="global_budget")
        )

    plan_payload = {
        "simulation_only": True,
        "budget": budget.to_dict(),
        "usage_by_class": {key.value: value for key, value in usage_by_class.items()},
        "overage_by_class": {key.value: value for key, value in overage_by_class.items()},
        "global_overage": global_overage,
        "pressure_snapshot": dict(pressure_snapshot),
        "pressure_tier": tier.to_dict(),
        "planned_demotions": [dict(item) for item in planned_demotions],
        "planned_evictions": [dict(item) for item in planned_evictions],
    }
    plan_hash = _hash_payload(plan_payload)
    plan = MemoryEconomicPlan(
        simulation_only=True,
        budget=budget,
        usage_by_class=usage_by_class,
        overage_by_class=overage_by_class,
        global_overage=global_overage,
        pressure_snapshot=pressure_snapshot,
        pressure_tier=tier,
        planned_demotions=tuple(planned_demotions),
        planned_evictions=tuple(planned_evictions),
        plan_hash=plan_hash,
    )
    if emit_introspection:
        emit_introspection_event(
            event_type=EventType.MEMORY_ECONOMICS,
            phase="memory",
            summary="Memory economics simulation emitted.",
            metadata={
                "plan_hash": plan_hash,
                "global_overage": global_overage,
                "pressure_tier": tier.name,
                "planned_demotions": len(planned_demotions),
                "planned_evictions": len(planned_evictions),
                "retention_cost_multiplier": tier.retention_cost_multiplier,
                "decay_multiplier": tier.decay_multiplier,
            },
            linked_artifact_ids=[plan_hash],
            path=introspection_path or DEFAULT_LOG_PATH,
        )
    return plan


def _ordered_candidates(entries: Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    return sorted(entries, key=lambda item: (_parse_timestamp(item.get("timestamp")), str(item.get("id", ""))))


def _ordered_global_candidates(
    entries_by_class: Mapping[MemoryClass, Sequence[Mapping[str, object]]],
) -> list[tuple[MemoryClass, Mapping[str, object]]]:
    weighted: list[tuple[int, datetime.datetime, str, MemoryClass, Mapping[str, object]]] = []
    for cls, entries in entries_by_class.items():
        policy = DEFAULT_CLASS_POLICIES.get(cls)
        priority = policy.eviction_priority if policy else 0
        for entry in entries:
            weighted.append(
                (
                    priority,
                    _parse_timestamp(entry.get("timestamp")),
                    str(entry.get("id", "")),
                    cls,
                    entry,
                )
            )
    weighted.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [(cls, entry) for _, _, _, cls, entry in weighted]


def _plan_moves(
    candidates: Sequence[Mapping[str, object]],
    source_class: MemoryClass,
    policies: Mapping[MemoryClass, MemoryClassPolicy],
    count: int,
    *,
    reason: str,
) -> list[dict[str, object]]:
    if count <= 0:
        return []
    if policies.get(source_class, MemoryClassPolicy(0, 0, "", ())).demotion_protected:
        return []
    target_class = _next_class(source_class)
    if target_class is None:
        return []
    moves = []
    for entry in candidates[:count]:
        moves.append(
            {
                "id": str(entry.get("id", "")),
                "from_class": source_class.value,
                "to_class": target_class.value,
                "reason": reason,
            }
        )
    return moves


def _plan_evictions(
    candidates: Sequence[tuple[MemoryClass, Mapping[str, object]]],
    count: int,
    *,
    reason: str,
) -> list[dict[str, object]]:
    planned = []
    for cls, entry in candidates[:count]:
        planned.append(
            {
                "id": str(entry.get("id", "")),
                "from_class": cls.value,
                "reason": reason,
            }
        )
    return planned


def _next_class(source_class: MemoryClass) -> MemoryClass | None:
    for idx, cls in enumerate(_DEMOTION_ORDER):
        if cls == source_class:
            if idx + 1 < len(_DEMOTION_ORDER):
                return _DEMOTION_ORDER[idx + 1]
            return None
    return None


def _parse_timestamp(value: object) -> datetime.datetime:
    if isinstance(value, datetime.datetime):
        return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(float(value), tz=datetime.timezone.utc)
    if isinstance(value, str):
        try:
            ts = datetime.datetime.fromisoformat(value)
            return ts if ts.tzinfo else ts.replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            return datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)
    return datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)


def _hash_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "MemoryClass",
    "MemoryClassPolicy",
    "MemoryBudget",
    "MemoryEconomicPlan",
    "PressureTier",
    "classify_memory",
    "simulate_memory_economics",
]
