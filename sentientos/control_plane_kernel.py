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
    ROLLBACK = "rollback"
    DAEMON_RESTART = "daemon_restart"
    PROPOSAL_EVALUATION = "proposal_evaluation"
    PROPOSAL_ADOPTION = "proposal_adoption"
    MANIFEST_OR_IDENTITY_MUTATION = "manifest_or_identity_mutation"
    FEDERATED_CONTROL = "federated_control"
    SPEC_AMENDMENT = "spec_amendment"
    PRIVILEGED_OPERATOR_CONTROL = "privileged_operator_control"


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
    def admission_decision_ref(self) -> str:
        return f"kernel_decision:{self.correlation_id}"

    @property
    def allowed(self) -> bool:
        return self.outcome == AdmissionOutcome.ALLOW

    def to_dict(self) -> dict[str, Any]:
        federation_context = self.delegated_outcomes.get("federation_context")
        proof_budget_context = self.delegated_outcomes.get("proof_budget_context")
        return {
            "event_type": "control_plane_decision",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "final_disposition": self.outcome.value,
            "outcome": self.outcome.value,
            "reason_codes": list(self.reason_codes),
            "delegate_checks_consulted": sorted(self.delegated_outcomes.keys()),
            "lifecycle_phase": self.current_phase.value,
            "current_phase": self.current_phase.value,
            "requested_phase": self.requested_phase.value,
            "authority_class": self.authority_class.value,
            "action_kind": self.action_kind,
            "actor_source": self.actor,
            "actor": self.actor,
            "execution_owner": self.actor,
            "target_subsystem": self.target_subsystem,
            "delegated_outcomes": dict(self.delegated_outcomes),
            "federation_context": dict(federation_context) if isinstance(federation_context, Mapping) else None,
            "proof_budget_context": dict(proof_budget_context) if isinstance(proof_budget_context, Mapping) else None,
            "correlation_id": self.correlation_id,
            "admission_decision_ref": self.admission_decision_ref,
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
        self._admission_history: set[tuple[str, str]] = set()

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
        validation_reason = self._validate_request(request)
        if validation_reason is not None:
            reasons.append(validation_reason)
            return self._finalize(request, AdmissionOutcome.QUARANTINE, reasons, delegated)

        correlation_id = str(
            request.metadata.get("correlation_id")
            or f"{request.actor}:{request.action_kind}:{request.target_subsystem}"
        )
        dedupe_key = (self._phase.value, correlation_id)
        if dedupe_key in self._admission_history:
            reasons.append("duplicate_admission_context")
            return self._finalize(request, AdmissionOutcome.DEFER, reasons, delegated, correlation_id=correlation_id)
        self._admission_history.add(dedupe_key)

        phase_reason, phase_outcome = self._evaluate_phase(request)
        if phase_reason:
            reasons.append(phase_reason)
        if phase_outcome is not None:
            decision = self._finalize(request, phase_outcome, reasons, delegated, correlation_id=correlation_id)
            return decision

        runtime, runtime_error = self._delegate_runtime_governor(request)
        if runtime_error:
            reasons.append(runtime_error)
            return self._finalize(request, AdmissionOutcome.DEFER, reasons, delegated, correlation_id=correlation_id)
        if runtime is not None:
            delegated["runtime_governor"] = runtime.to_dict()
            if not runtime.allowed:
                reasons.append(f"runtime_governor:{runtime.reason}")
                return self._finalize(request, AdmissionOutcome.DENY, reasons, delegated, correlation_id=correlation_id)

        budget_decision, budget_error = self._delegate_proof_budget(request)
        if budget_error:
            reasons.append(budget_error)
            return self._finalize(request, AdmissionOutcome.DEFER, reasons, delegated, correlation_id=correlation_id)
        if budget_decision is not None:
            delegated["proof_budget_context"] = {
                "pipeline": request.proof_budget_context.get("run_context", {}).get("pipeline")
                if isinstance(request.proof_budget_context, Mapping)
                else None,
                "router_attempt": request.proof_budget_context.get("run_context", {}).get("router_attempt")
                if isinstance(request.proof_budget_context, Mapping)
                else None,
            }
            delegated["proof_budget_governor"] = {
                "mode": budget_decision.mode,
                "k_effective": budget_decision.k_effective,
                "m_effective": budget_decision.m_effective,
                "allow_escalation": budget_decision.allow_escalation,
                "decision_reasons": list(budget_decision.decision_reasons),
            }
            if budget_decision.mode == "diagnostics_only" and bool(request.metadata.get("require_admissible", True)):
                reasons.append("proof_budget:diagnostics_only")
                return self._finalize(request, AdmissionOutcome.DEFER, reasons, delegated, correlation_id=correlation_id)

        denial = str(request.metadata.get("federated_denial_cause") or "")
        if request.authority_class == AuthorityClass.FEDERATED_CONTROL:
            delegated["federation_context"] = {
                "federation_origin": request.federation_origin,
                "scope": request.metadata.get("scope"),
            }
            if not request.federation_origin:
                reasons.append("federation_origin_missing")
                return self._finalize(request, AdmissionOutcome.QUARANTINE, reasons, delegated, correlation_id=correlation_id)
        if request.authority_class == AuthorityClass.FEDERATED_CONTROL and denial and denial not in {"none", ""}:
            reasons.append(f"federation_governance:{denial}")
            return self._finalize(request, AdmissionOutcome.DENY, reasons, delegated, correlation_id=correlation_id)

        reasons.append("admitted")
        return self._finalize(request, AdmissionOutcome.ALLOW, reasons, delegated, correlation_id=correlation_id)

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
        if request.startup_symbol and self._phase != LifecyclePhase.MAINTENANCE:
            guarded = self._finalize(
                request,
                AdmissionOutcome.DEFER,
                ["startup_mediation_required"],
                dict(decision.delegated_outcomes),
                correlation_id=decision.correlation_id,
            )
            return guarded, None
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
            AuthorityClass.MANIFEST_OR_IDENTITY_MUTATION,
            AuthorityClass.SPEC_AMENDMENT,
        }
        if startup_bound and not startup.active and self._phase == LifecyclePhase.RUNTIME:
            return "startup_bound_requires_maintenance", AdmissionOutcome.DEFER
        return None, None

    def _delegate_runtime_governor(self, request: ControlActionRequest) -> tuple[GovernorDecision | None, str | None]:
        action_map = {
            AuthorityClass.REPAIR: "repair_action",
            AuthorityClass.ROLLBACK: "repair_action",
            AuthorityClass.DAEMON_RESTART: "restart_daemon",
            AuthorityClass.FEDERATED_CONTROL: "federated_control",
            AuthorityClass.PROPOSAL_ADOPTION: "amendment_apply",
            AuthorityClass.MANIFEST_OR_IDENTITY_MUTATION: "amendment_apply",
            AuthorityClass.PROPOSAL_EVALUATION: "control_plane_task",
            AuthorityClass.SPEC_AMENDMENT: "control_plane_task",
            AuthorityClass.PRIVILEGED_OPERATOR_CONTROL: "control_plane_task",
        }
        action_class = action_map.get(request.authority_class)
        if action_class is None:
            return None, None
        if not hasattr(self._runtime_governor, "admit_action"):
            return None, "runtime_governor_unavailable"
        metadata = dict(request.metadata)
        if request.federation_origin:
            metadata.setdefault("peer_name", request.federation_origin)
            metadata.setdefault("scope", "federated")
        try:
            return self._runtime_governor.admit_action(
                action_class,
                request.actor,
                str(request.metadata.get("correlation_id") or f"{request.actor}:{request.action_kind}:{request.target_subsystem}"),
                metadata=metadata,
            ), None
        except Exception:
            return None, "runtime_governor_error"

    @staticmethod
    def _delegate_proof_budget(request: ControlActionRequest) -> tuple["BudgetDecision | None", str | None]:
        if request.proof_budget_context is None:
            return None, None
        try:
            from codex.proof_budget_governor import decide_budget
        except Exception:
            return None, "proof_budget_delegate_unavailable"

        payload = request.proof_budget_context
        config = payload.get("config")
        pressure_state = payload.get("pressure_state")
        run_context = payload.get("run_context")
        if config is None or pressure_state is None or not isinstance(run_context, Mapping):
            return None, "proof_budget_context_invalid"
        try:
            return decide_budget(config=config, pressure_state=pressure_state, run_context=run_context), None
        except Exception:
            return None, "proof_budget_delegate_error"

    def _finalize(
        self,
        request: ControlActionRequest,
        outcome: AdmissionOutcome,
        reasons: list[str],
        delegated: dict[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> ControlActionDecision:
        corr = correlation_id or str(
            request.metadata.get("correlation_id")
            or f"{request.actor}:{request.action_kind}:{request.target_subsystem}"
        )
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
            correlation_id=corr,
        )
        decision_payload = decision.to_dict()
        append_status = "ok"
        try:
            self._append(decision_payload)
        except OSError:
            append_status = "write_error"
            decision_payload = {
                **decision_payload,
                "reason_codes": sorted(set(list(decision.reason_codes) + ["decision_log_write_failed"])),
                "delegate_checks_consulted": sorted(set(decision_payload.get("delegate_checks_consulted", []) + ["decision_log"])),
            }
        self._emit_decision_event(decision_payload, append_status=append_status)
        return decision

    def _append(self, payload: Mapping[str, Any]) -> None:
        with self._decisions_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(payload), sort_keys=True) + "\n")

    @staticmethod
    def _emit_decision_event(payload: Mapping[str, Any], *, append_status: str) -> None:
        try:
            from sentientos.daemons import pulse_bus

            pulse_bus.publish(
                {
                    "source_daemon": "control_plane_kernel",
                    "priority": "info" if append_status == "ok" else "warning",
                    "event_type": "control_plane_decision",
                    "payload": {
                        "action_kind": payload.get("action_kind"),
                        "actor_source": payload.get("actor_source"),
                        "lifecycle_phase": payload.get("lifecycle_phase"),
                        "target_subsystem": payload.get("target_subsystem"),
                        "final_disposition": payload.get("final_disposition"),
                        "reason_codes": payload.get("reason_codes", []),
                        "delegate_checks_consulted": payload.get("delegate_checks_consulted", []),
                        "correlation_id": payload.get("correlation_id"),
                        "timestamp": payload.get("timestamp"),
                        "federation_context": payload.get("federation_context"),
                        "proof_budget_context": payload.get("proof_budget_context"),
                        "decision_log_append_status": append_status,
                    },
                }
            )
        except Exception:
            return

    @staticmethod
    def _validate_request(request: ControlActionRequest) -> str | None:
        if not isinstance(request.action_kind, str) or not request.action_kind.strip():
            return "invalid_action_kind"
        if not isinstance(request.actor, str) or not request.actor.strip():
            return "invalid_actor"
        if not isinstance(request.target_subsystem, str) or not request.target_subsystem.strip():
            return "invalid_target_subsystem"
        if not isinstance(request.metadata, dict):
            return "invalid_metadata"
        return None


_KERNEL: ControlPlaneKernel | None = None


def get_control_plane_kernel() -> ControlPlaneKernel:
    global _KERNEL
    if _KERNEL is None:
        _KERNEL = ControlPlaneKernel()
    return _KERNEL


def reset_control_plane_kernel() -> None:
    global _KERNEL
    _KERNEL = None
