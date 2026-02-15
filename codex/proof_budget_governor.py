"""Deterministic proof-budget governor for staged routing flows."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

GOVERNOR_VERSION = "v1"
DEFAULT_PRESSURE_STATE_PATH = Path("glow/routing/pressure_state.json")


@dataclass(slots=True, frozen=True)
class BudgetDecision:
    k_effective: int
    m_effective: int
    allow_escalation: bool
    mode: str
    decision_reasons: list[str]
    governor_version: str = GOVERNOR_VERSION


@dataclass(slots=True, frozen=True)
class GovernorConfig:
    configured_k: int
    configured_m: int
    max_k: int
    escalation_enabled: bool
    mode: str
    admissible_collapse_runs: int
    min_m: int
    diagnostics_k: int
    pressure_window: int = 6
    proof_burn_spike_runs: int = 2
    escalation_cluster_runs: int = 2


@dataclass(slots=True)
class PressureState:
    consecutive_no_admissible: int = 0
    recent_runs: list[dict[str, Any]] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["recent_runs"] = list(self.recent_runs or [])
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "PressureState":
        return cls(
            consecutive_no_admissible=max(0, int(payload.get("consecutive_no_admissible", 0))),
            recent_runs=[dict(item) for item in payload.get("recent_runs", []) if isinstance(item, Mapping)],
        )


def _flag_enabled(value: str) -> bool:
    return value not in {"0", "false", "False"}


def governor_config_from_env(*, configured_k: int, configured_m: int) -> GovernorConfig:
    return GovernorConfig(
        configured_k=max(1, int(configured_k)),
        configured_m=max(1, int(configured_m)),
        max_k=max(int(os.getenv("SENTIENTOS_ROUTER_MAX_K", "9")), 1),
        escalation_enabled=_flag_enabled(os.getenv("SENTIENTOS_ROUTER_ESCALATE_ON_ALL_FAIL_A", "1")),
        mode=str(os.getenv("SENTIENTOS_GOVERNOR_MODE", "auto") or "auto"),
        admissible_collapse_runs=max(1, int(os.getenv("SENTIENTOS_GOVERNOR_ADMISSIBLE_COLLAPSE_RUNS", "3"))),
        min_m=max(1, int(os.getenv("SENTIENTOS_GOVERNOR_MIN_M", "1"))),
        diagnostics_k=max(1, int(os.getenv("SENTIENTOS_GOVERNOR_DIAGNOSTICS_K", "4"))),
    )


def load_pressure_state(path: Path | None = None) -> PressureState:
    state_path = path or DEFAULT_PRESSURE_STATE_PATH
    if not state_path.exists():
        return PressureState(recent_runs=[])
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return PressureState(recent_runs=[])
    if not isinstance(payload, Mapping):
        return PressureState(recent_runs=[])
    return PressureState.from_payload(payload)


def save_pressure_state(state: PressureState, path: Path | None = None) -> None:
    state_path = path or DEFAULT_PRESSURE_STATE_PATH
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state.as_dict(), sort_keys=True, indent=2), encoding="utf-8")


def _recent_runs(state: PressureState, *, window: int) -> list[dict[str, Any]]:
    runs = list(state.recent_runs or [])
    if window <= 0:
        return runs
    return runs[-window:]


def decide_budget(
    *,
    config: GovernorConfig,
    pressure_state: PressureState,
    run_context: Mapping[str, Any],
) -> BudgetDecision:
    del run_context  # Explicitly accepted for deterministic context-keyed decisions.

    reasons: list[str] = []
    k_effective = config.configured_k
    m_effective = config.configured_m
    allow_escalation = bool(config.escalation_enabled)
    mode = "normal"

    recent = _recent_runs(pressure_state, window=config.pressure_window)
    burn_spikes = sum(
        1
        for item in recent
        if bool(item.get("proof_burn_spike"))
    )
    escalation_runs = sum(1 for item in recent if bool(item.get("escalated")))

    proof_burn_spike = burn_spikes >= config.proof_burn_spike_runs
    escalation_cluster = escalation_runs >= config.escalation_cluster_runs
    admissible_collapse = pressure_state.consecutive_no_admissible >= config.admissible_collapse_runs

    requested_mode = config.mode.strip().lower()
    if requested_mode == "diagnostics_only":
        admissible_collapse = True
        reasons.append("forced_mode")
    elif requested_mode == "constrained":
        proof_burn_spike = True
        reasons.append("forced_mode")
    elif requested_mode not in {"auto", "normal", ""}:
        reasons.append("invalid_mode_fallback")

    if proof_burn_spike:
        m_effective = max(config.min_m, config.configured_m - 1)
        allow_escalation = False
        mode = "constrained"
        reasons.append("proof_burn_spike")

    if escalation_cluster:
        k_effective = min(k_effective, 3)
        allow_escalation = False
        if mode == "normal":
            mode = "constrained"
        reasons.append("escalation_cluster")

    if admissible_collapse:
        k_effective = max(k_effective, min(config.max_k, config.diagnostics_k))
        m_effective = 0
        allow_escalation = False
        mode = "diagnostics_only"
        reasons.append("admissible_collapse")

    return BudgetDecision(
        k_effective=max(1, min(k_effective, config.max_k)),
        m_effective=max(0, m_effective),
        allow_escalation=allow_escalation,
        mode=mode,
        decision_reasons=sorted(set(reasons)),
    )


def update_pressure_state(
    *,
    prior: PressureState,
    decision: BudgetDecision,
    router_telemetry: Mapping[str, Any],
    router_status: str,
    run_context: Mapping[str, Any],
    config: GovernorConfig,
) -> PressureState:
    no_admissible = router_status != "selected"
    consecutive_no_admissible = prior.consecutive_no_admissible + 1 if no_admissible else 0
    event = {
        "pipeline": str(run_context.get("pipeline", "unknown")),
        "capability": str(run_context.get("capability") or run_context.get("spec_id") or "unknown"),
        "router_attempt": int(run_context.get("router_attempt", 1)),
        "router_status": router_status,
        "mode": decision.mode,
        "proof_burn_spike": "proof_burn_spike" in decision.decision_reasons,
        "escalated": bool(router_telemetry.get("escalated", False)),
        "stage_b_evaluations": int(router_telemetry.get("stage_b_evaluations", 0)),
    }
    recent = _recent_runs(prior, window=config.pressure_window - 1)
    recent.append(event)
    return PressureState(
        consecutive_no_admissible=consecutive_no_admissible,
        recent_runs=recent,
    )


def build_governor_event(
    *,
    decision: BudgetDecision,
    run_context: Mapping[str, Any],
    router_telemetry: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "event_type": "proof_budget_governor",
        "pipeline": str(run_context.get("pipeline", "unknown")),
        "capability": str(run_context.get("capability") or run_context.get("spec_id") or "unknown"),
        "router_attempt": int(run_context.get("router_attempt", 1)),
        "governor": {
            "mode": decision.mode,
            "k_effective": decision.k_effective,
            "m_effective": decision.m_effective,
            "allow_escalation": decision.allow_escalation,
            "reasons": list(decision.decision_reasons),
            "governor_version": decision.governor_version,
        },
        "router_telemetry": dict(router_telemetry),
    }
