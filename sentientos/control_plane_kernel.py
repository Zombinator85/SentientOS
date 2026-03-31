from __future__ import annotations

import json
import os
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping

from sentientos.codex_startup_guard import codex_runtime_mediation, codex_startup_state
from sentientos.runtime_governor import GovernorDecision, RuntimeGovernor, get_runtime_governor

if TYPE_CHECKING:
    from codex.proof_budget_governor import BudgetDecision


class LifecyclePhase(str, Enum):
    BOOTSTRAP = "bootstrap"
    RUNTIME = "runtime"
    MAINTENANCE = "maintenance"
    SHUTDOWN = "shutdown"


class AuthorityClass(str, Enum):
    OBSERVATION = "observation"
    REPAIR = "repair"
    DAEMON_RESTART = "daemon_restart"
    PROPOSAL_EVALUATION = "proposal_evaluation"
    PROPOSAL_ADOPTION = "proposal_adoption"
    FEDERATED_CONTROL = "federated_control"
    SPEC_AMENDMENT = "spec_amendment"


class AdmissionOutcome(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    DEFER = "defer"
    QUARANTINE = "quarantine"


@dataclass(frozen=True, slots=True)
class ControlActionRequest:
    action_kind: str
    authority_class: AuthorityClass
    actor: str
    target_subsystem: str
    requested_phase: LifecyclePhase
    metadata: dict[str, Any] = field(default_factory=dict)
    federation_origin: str | None = None
    proof_budget_context: dict[str, Any] | None = None
    startup_symbol: str | None = None


@dataclass(frozen=True, slots=True)
class ControlActionDecision:
    outcome: AdmissionOutcome
    reason_codes: tuple[str, ...]
    current_phase: LifecyclePhase
    requested_phase: LifecyclePhase
    authority_class: AuthorityClass
    action_kind: str
    actor: str
    target_subsystem: str
    delegated_outcomes: dict[str, Any]
    correlation_id: str

    @property
    def allowed(self) -> bool:
        return self.outcome == AdmissionOutcome.ALLOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": "control_plane_decision",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "outcome": self.outcome.value,
            "reason_codes": list(self.reason_codes),
            "current_phase": self.current_phase.value,
            "requested_phase": self.requested_phase.value,
            "authority_class": self.authority_class.value,
            "action_kind": self.action_kind,
            "actor": self.actor,
            "target_subsystem": self.target_subsystem,
            "delegated_outcomes": dict(self.delegated_outcomes),
            "correlation_id": self.correlation_id,
        }


class ControlPlaneKernel:
    """Phase-aware control-plane admission broker.

    This layer orchestrates existing governors/guards and records a machine-readable
    decision row for every sensitive action request.
    """

    def __init__(
        self,
        *,
        runtime_governor: RuntimeGovernor | None = None,
        decisions_path: Path | None = None,
        phase: LifecyclePhase = LifecyclePhase.RUNTIME,
    ) -> None:
        self._phase = phase
        self._runtime_governor = runtime_governor or get_runtime_governor()
        root = Path(os.getenv("SENTIENTOS_CONTROL_KERNEL_ROOT", "glow/control_plane"))
        self._decisions_path = decisions_path or (root / "kernel_decisions.jsonl")
        self._decisions_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def phase(self) -> LifecyclePhase:
        return self._phase

    def set_phase(self, phase: LifecyclePhase, *, actor: str = "control_plane_kernel") -> None:
        self._phase = phase
        self._append(
            {
                "event_type": "control_plane_phase",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "phase": phase.value,
                "actor": actor,
            }
        )

    def admit(self, request: ControlActionRequest) -> ControlActionDecision:
        reasons: list[str] = []
        delegated: dict[str, Any] = {}

        phase_reason, phase_outcome = self._evaluate_phase(request)
        if phase_reason:
            reasons.append(phase_reason)
        if phase_outcome is not None:
            decision = self._finalize(request, phase_outcome, reasons, delegated)
            return decision

        runtime = self._delegate_runtime_governor(request)
        if runtime is not None:
            delegated["runtime_governor"] = runtime.to_dict()
            if not runtime.allowed:
                reasons.append(f"runtime_governor:{runtime.reason}")
                return self._finalize(request, AdmissionOutcome.DENY, reasons, delegated)

        budget_decision = self._delegate_proof_budget(request)
        if budget_decision is not None:
            delegated["proof_budget_governor"] = {
                "mode": budget_decision.mode,
                "k_effective": budget_decision.k_effective,
                "m_effective": budget_decision.m_effective,
                "allow_escalation": budget_decision.allow_escalation,
                "decision_reasons": list(budget_decision.decision_reasons),
            }
            if budget_decision.mode == "diagnostics_only" and bool(request.metadata.get("require_admissible", True)):
                reasons.append("proof_budget:diagnostics_only")
                return self._finalize(request, AdmissionOutcome.DEFER, reasons, delegated)

        denial = str(request.metadata.get("federated_denial_cause") or "")
        if request.authority_class == AuthorityClass.FEDERATED_CONTROL and denial and denial not in {"none", ""}:
            reasons.append(f"federation_governance:{denial}")
            return self._finalize(request, AdmissionOutcome.DENY, reasons, delegated)

        reasons.append("admitted")
        return self._finalize(request, AdmissionOutcome.ALLOW, reasons, delegated)

    def admit_and_execute(
        self,
        request: ControlActionRequest,
        *,
        execute: Callable[[], Any] | None = None,
    ) -> tuple[ControlActionDecision, Any | None]:
        decision = self.admit(request)
        if not decision.allowed:
            return decision, None
        if execute is None:
            return decision, None
        symbol = request.startup_symbol
        ctx = codex_runtime_mediation(symbol) if symbol and self._phase == LifecyclePhase.MAINTENANCE else nullcontext()
        with ctx:
            return decision, execute()

    def _evaluate_phase(self, request: ControlActionRequest) -> tuple[str | None, AdmissionOutcome | None]:
        if request.requested_phase != self._phase:
            return "phase_mismatch", AdmissionOutcome.DEFER
        startup = codex_startup_state()
        startup_bound = request.authority_class in {
            AuthorityClass.PROPOSAL_EVALUATION,
            AuthorityClass.PROPOSAL_ADOPTION,
            AuthorityClass.SPEC_AMENDMENT,
        }
        if startup_bound and not startup.active and self._phase == LifecyclePhase.RUNTIME:
            return "startup_bound_requires_maintenance", AdmissionOutcome.DEFER
        return None, None

    def _delegate_runtime_governor(self, request: ControlActionRequest) -> GovernorDecision | None:
        action_map = {
            AuthorityClass.REPAIR: "repair_action",
            AuthorityClass.DAEMON_RESTART: "restart_daemon",
            AuthorityClass.FEDERATED_CONTROL: "federated_control",
            AuthorityClass.PROPOSAL_ADOPTION: "amendment_apply",
            AuthorityClass.PROPOSAL_EVALUATION: "control_plane_task",
            AuthorityClass.SPEC_AMENDMENT: "control_plane_task",
        }
        action_class = action_map.get(request.authority_class)
        if action_class is None:
            return None
        metadata = dict(request.metadata)
        if request.federation_origin:
            metadata.setdefault("peer_name", request.federation_origin)
            metadata.setdefault("scope", "federated")
        return self._runtime_governor.admit_action(
            action_class,
            request.actor,
            str(request.metadata.get("correlation_id") or f"{request.actor}:{request.action_kind}:{request.target_subsystem}"),
            metadata=metadata,
        )

    @staticmethod
    def _delegate_proof_budget(request: ControlActionRequest) -> "BudgetDecision | None":
        if request.proof_budget_context is None:
            return None
        from codex.proof_budget_governor import decide_budget

        payload = request.proof_budget_context
        config = payload.get("config")
        pressure_state = payload.get("pressure_state")
        run_context = payload.get("run_context")
        if config is None or pressure_state is None or not isinstance(run_context, Mapping):
            return None
        return decide_budget(config=config, pressure_state=pressure_state, run_context=run_context)

    def _finalize(
        self,
        request: ControlActionRequest,
        outcome: AdmissionOutcome,
        reasons: list[str],
        delegated: dict[str, Any],
    ) -> ControlActionDecision:
        decision = ControlActionDecision(
            outcome=outcome,
            reason_codes=tuple(dict.fromkeys(reasons)),
            current_phase=self._phase,
            requested_phase=request.requested_phase,
            authority_class=request.authority_class,
            action_kind=request.action_kind,
            actor=request.actor,
            target_subsystem=request.target_subsystem,
            delegated_outcomes=delegated,
            correlation_id=str(request.metadata.get("correlation_id") or f"{request.actor}:{request.action_kind}:{request.target_subsystem}"),
        )
        self._append(decision.to_dict())
        return decision

    def _append(self, payload: Mapping[str, Any]) -> None:
        with self._decisions_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(payload), sort_keys=True) + "\n")


_KERNEL: ControlPlaneKernel | None = None


def get_control_plane_kernel() -> ControlPlaneKernel:
    global _KERNEL
    if _KERNEL is None:
        _KERNEL = ControlPlaneKernel()
    return _KERNEL


def reset_control_plane_kernel() -> None:
    global _KERNEL
    _KERNEL = None
