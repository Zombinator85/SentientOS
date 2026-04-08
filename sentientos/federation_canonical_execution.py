from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from sentientos.control_plane_kernel import (
    AuthorityClass,
    ControlActionRequest,
    LifecyclePhase,
    get_control_plane_kernel,
)


BOUNDED_FEDERATION_CANONICAL_ACTIONS: tuple[str, ...] = (
    "sentientos.federation.restart_daemon_request",
    "sentientos.federation.governance_digest_or_quorum_denial_gate",
    "sentientos.federation.epoch_or_trust_posture_gate",
)


_CANONICAL_HANDLER_REGISTRY: dict[str, str] = {
    "sentientos.federation.restart_daemon_request": "sentientos.daemons.pulse_federation._canonical_restart_daemon_handler.v1",
    "sentientos.federation.governance_digest_or_quorum_denial_gate": "sentientos.daemons.pulse_federation._canonical_governance_gate_handler.v1",
    "sentientos.federation.epoch_or_trust_posture_gate": "sentientos.daemons.pulse_federation._canonical_epoch_trust_gate_handler.v1",
}


_REQUIRED_METADATA_FIELDS: tuple[str, ...] = ("correlation_id", "subject", "scope")


@dataclass(frozen=True, slots=True)
class FederationCanonicalExecutionResult:
    typed_action_id: str
    canonical_router: str
    canonical_handler: str
    canonical_outcome: str
    admitted: bool
    admission_decision_ref: str
    decision_reason_codes: tuple[str, ...]
    delegated_outcomes: dict[str, Any]
    side_effect_status: str
    handler_result: Any | None = None
    failure: dict[str, str] | None = None


class FederationCanonicalExecutionRouter:
    ROUTER_ID = "federation_canonical_execution_router.v1"

    def execute(
        self,
        *,
        typed_action_id: str,
        peer_name: str,
        action_kind: str,
        target_subsystem: str,
        correlation_id: str,
        metadata: Mapping[str, object],
        handler: Callable[[], Any],
    ) -> FederationCanonicalExecutionResult:
        normalized_typed_action_id = str(typed_action_id or "").strip()
        if normalized_typed_action_id not in BOUNDED_FEDERATION_CANONICAL_ACTIONS:
            raise ValueError(f"out_of_scope_or_unregistered_typed_action:{normalized_typed_action_id or 'missing'}")
        canonical_handler = _CANONICAL_HANDLER_REGISTRY.get(normalized_typed_action_id)
        if not canonical_handler:
            raise ValueError(f"missing_canonical_registration:{normalized_typed_action_id}")

        metadata_payload = dict(metadata)
        for field in _REQUIRED_METADATA_FIELDS:
            if not str(metadata_payload.get(field) or "").strip():
                raise ValueError(f"missing_required_metadata:{field}")

        request = ControlActionRequest(
            action_kind=action_kind,
            authority_class=AuthorityClass.FEDERATED_CONTROL,
            actor=peer_name,
            target_subsystem=target_subsystem,
            requested_phase=LifecyclePhase.RUNTIME,
            federation_origin=peer_name,
            metadata={
                **metadata_payload,
                "typed_action_id": normalized_typed_action_id,
                "canonical_execution": {
                    "router": self.ROUTER_ID,
                    "required_metadata_fields": list(_REQUIRED_METADATA_FIELDS),
                },
            },
        )
        decision = get_control_plane_kernel().admit(request)
        admission_decision_ref = getattr(decision, "admission_decision_ref", f"kernel_decision:{decision.correlation_id}")

        if not decision.allowed:
            denied = FederationCanonicalExecutionResult(
                typed_action_id=normalized_typed_action_id,
                canonical_router=self.ROUTER_ID,
                canonical_handler=canonical_handler,
                canonical_outcome="denied_pre_execution",
                admitted=False,
                admission_decision_ref=admission_decision_ref,
                decision_reason_codes=tuple(decision.reason_codes),
                delegated_outcomes=dict(decision.delegated_outcomes),
                side_effect_status="no_side_effect",
            )
            _append_canonical_execution_row(peer_name=peer_name, correlation_id=correlation_id, result=denied)
            return denied

        try:
            handler_result = handler()
        except Exception as exc:
            failed = FederationCanonicalExecutionResult(
                typed_action_id=normalized_typed_action_id,
                canonical_router=self.ROUTER_ID,
                canonical_handler=canonical_handler,
                canonical_outcome="admitted_failed",
                admitted=True,
                admission_decision_ref=admission_decision_ref,
                decision_reason_codes=tuple(decision.reason_codes),
                delegated_outcomes=dict(decision.delegated_outcomes),
                side_effect_status="unknown_partial_side_effects_possible",
                failure={"exception_type": exc.__class__.__name__, "message": str(exc)},
            )
            _append_canonical_execution_row(peer_name=peer_name, correlation_id=correlation_id, result=failed)
            return failed

        succeeded = FederationCanonicalExecutionResult(
            typed_action_id=normalized_typed_action_id,
            canonical_router=self.ROUTER_ID,
            canonical_handler=canonical_handler,
            canonical_outcome="admitted_succeeded",
            admitted=True,
            admission_decision_ref=admission_decision_ref,
            decision_reason_codes=tuple(decision.reason_codes),
            delegated_outcomes=dict(decision.delegated_outcomes),
            side_effect_status="side_effect_committed" if bool(handler_result) else "no_side_effect",
            handler_result=handler_result,
        )
        _append_canonical_execution_row(peer_name=peer_name, correlation_id=correlation_id, result=succeeded)
        return succeeded


def _runtime_root() -> Path:
    return Path(os.getenv("SENTIENTOS_FEDERATION_ROOT", "/glow/federation"))


def _append_canonical_execution_row(
    *,
    peer_name: str,
    correlation_id: str,
    result: FederationCanonicalExecutionResult,
) -> None:
    root = _runtime_root()
    root.mkdir(parents=True, exist_ok=True)
    row = {
        "event_type": "federation_canonical_execution",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "peer_name": peer_name,
        "correlation_id": correlation_id,
        "typed_action_id": result.typed_action_id,
        "canonical_router": result.canonical_router,
        "canonical_handler": result.canonical_handler,
        "canonical_outcome": result.canonical_outcome,
        "admitted": result.admitted,
        "admission_decision_ref": result.admission_decision_ref,
        "decision_reason_codes": list(result.decision_reason_codes),
        "delegated_outcomes": dict(result.delegated_outcomes),
        "side_effect_status": result.side_effect_status,
        "failure": dict(result.failure) if isinstance(result.failure, Mapping) else None,
        "proof_linkage_present": bool(result.typed_action_id and result.admission_decision_ref and result.canonical_handler),
    }
    with (root / "canonical_execution.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


_ROUTER: FederationCanonicalExecutionRouter | None = None


def get_federation_canonical_execution_router() -> FederationCanonicalExecutionRouter:
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = FederationCanonicalExecutionRouter()
    return _ROUTER


def reset_federation_canonical_execution_router() -> None:
    global _ROUTER
    _ROUTER = None


__all__ = [
    "BOUNDED_FEDERATION_CANONICAL_ACTIONS",
    "FederationCanonicalExecutionResult",
    "FederationCanonicalExecutionRouter",
    "get_federation_canonical_execution_router",
    "reset_federation_canonical_execution_router",
]
