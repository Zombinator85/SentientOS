from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class FederationTypedAction:
    action_id: str
    intent: str
    mutation_control_domain: str
    authority_class: str
    lifecycle_context: str
    canonical_entry_surface: str
    proof_visible_boundary: str

    def to_dict(self) -> dict[str, str]:
        return {
            "action_id": self.action_id,
            "intent": self.intent,
            "mutation_control_domain": self.mutation_control_domain,
            "authority_class": self.authority_class,
            "lifecycle_context": self.lifecycle_context,
            "canonical_entry_surface": self.canonical_entry_surface,
            "proof_visible_boundary": self.proof_visible_boundary,
        }


FEDERATION_TYPED_ACTIONS: tuple[FederationTypedAction, ...] = (
    FederationTypedAction(
        action_id="sentientos.federation.restart_daemon_request",
        intent="federation.restart_daemon_request",
        mutation_control_domain="federation_mutation_control_slice",
        authority_class="federated_control",
        lifecycle_context="runtime.inbound_control",
        canonical_entry_surface="sentientos.daemons.pulse_federation.ingest_remote_event",
        proof_visible_boundary="glow/federation/ingest_classifications.jsonl:event_type+typed_action_id",
    ),
    FederationTypedAction(
        action_id="sentientos.federation.governance_digest_or_quorum_denial_gate",
        intent="federation.governance_digest_or_quorum_denial_gate",
        mutation_control_domain="federation_mutation_control_slice",
        authority_class="federated_control",
        lifecycle_context="runtime.control_mediation",
        canonical_entry_surface="sentientos.control_plane_kernel.ControlPlaneKernel.admit(authority_class=FEDERATED_CONTROL)",
        proof_visible_boundary="glow/control_plane/kernel_decisions.jsonl:reason_codes+delegated_outcomes",
    ),
    FederationTypedAction(
        action_id="sentientos.federation.epoch_or_trust_posture_gate",
        intent="federation.epoch_or_trust_posture_gate",
        mutation_control_domain="federation_mutation_control_slice",
        authority_class="federated_control",
        lifecycle_context="runtime.inbound_epoch_gate",
        canonical_entry_surface="sentientos.control_plane_kernel.ControlPlaneKernel.admit(authority_class=FEDERATED_CONTROL)",
        proof_visible_boundary="glow/control_plane/kernel_decisions.jsonl:reason_codes+delegated_outcomes.federation_context",
    ),
    FederationTypedAction(
        action_id="sentientos.federation.replay_or_receipt_consistency_gate",
        intent="federation.replay_or_receipt_consistency_gate",
        mutation_control_domain="federation_mutation_control_slice",
        authority_class="federated_control",
        lifecycle_context="runtime.replay_receipt_consistency_gate",
        canonical_entry_surface="sentientos.control_plane_kernel.ControlPlaneKernel.admit(authority_class=FEDERATED_CONTROL)",
        proof_visible_boundary="glow/federation/canonical_execution.jsonl:canonical_handler+admission_decision_ref",
    ),
    FederationTypedAction(
        action_id="sentientos.federation.ingest_replay_admission_gate",
        intent="federation.ingest_replay_admission_gate",
        mutation_control_domain="federation_mutation_control_slice",
        authority_class="federated_control",
        lifecycle_context="runtime.ingest_replay_admission_gate",
        canonical_entry_surface="sentientos.daemons.pulse_federation.ingest_remote_event",
        proof_visible_boundary="glow/federation/ingest_classifications.jsonl:event_type+typed_action_id",
    ),
)

FEDERATION_TYPED_ACTION_REGISTRY: dict[str, FederationTypedAction] = {
    action.action_id: action for action in FEDERATION_TYPED_ACTIONS
}

_GOVERNANCE_DENIAL_CAUSES = {
    "digest_mismatch",
    "digest_mismatch_advisory",
    "digest_mismatch_observed",
    "quorum_failure",
    "quorum_warning",
    "quorum_observed",
    "trust_epoch",
    "trust_epoch_advisory",
    "trust_epoch_observed",
}


def resolve_federation_typed_action_id(
    *,
    payload_action: str = "",
    denial_cause: str = "",
    trust_epoch_classification: str = "",
    replay_classification: str = "",
    receipt_consistency_classification: str = "",
) -> str | None:
    action = payload_action.strip().lower()
    if action == "restart_daemon":
        return "sentientos.federation.restart_daemon_request"
    denial = denial_cause.strip().lower()
    if denial in _GOVERNANCE_DENIAL_CAUSES:
        return "sentientos.federation.governance_digest_or_quorum_denial_gate"
    trust = trust_epoch_classification.strip().lower()
    if trust and trust not in {"trusted", "ok", "allow"}:
        return "sentientos.federation.epoch_or_trust_posture_gate"
    replay = replay_classification.strip().lower()
    if replay in {
        "incompatible_replay_policy",
        "peer_too_stale_for_replay_horizon",
        "peer_outside_accepted_replay_horizon",
        "duplicate_event_hash",
    }:
        return "sentientos.federation.ingest_replay_admission_gate"
    receipt = receipt_consistency_classification.strip().lower()
    if receipt in {
        "confirmed_equivocation",
        "protocol_claim_conflict",
        "replay_claim_conflict",
    }:
        return "sentientos.federation.replay_or_receipt_consistency_gate"
    return None


def federation_typed_action_diagnostic() -> dict[str, Any]:
    chosen = [action.to_dict() for action in FEDERATION_TYPED_ACTIONS]
    return {
        "slice_id": "federation_mutation_control_slice",
        "typed_identity_status": "bounded_initial_registration",
        "chosen_intents": chosen,
        "entry_surface_emissions": [
            {
                "surface": "sentientos.daemons.pulse_federation.ingest_remote_event",
                "emits_action_ids": ["sentientos.federation.restart_daemon_request"],
            },
            {
                "surface": "sentientos.control_plane_kernel.ControlPlaneKernel.admit(authority_class=FEDERATED_CONTROL)",
                "emits_action_ids": [
                    "sentientos.federation.governance_digest_or_quorum_denial_gate",
                    "sentientos.federation.epoch_or_trust_posture_gate",
                    "sentientos.federation.replay_or_receipt_consistency_gate",
                ],
            },
            {
                "surface": "sentientos.daemons.pulse_federation.ingest_remote_event(replay/duplicate gate)",
                "emits_action_ids": ["sentientos.federation.ingest_replay_admission_gate"],
            },
        ],
        "untyped_out_of_scope_intents": [
            "federation envelope serialization/transport internals",
            "non-control federation summary/report generation",
            "cross-node replay synthesis beyond control admission decisions",
        ],
        "non_sovereign": True,
        "execution_router_migration": "bounded_canonical_execution_enabled_for_initial_intent_set",
        "registry_validation_errors": validate_federation_typed_action_registry(),
    }


def validate_federation_typed_action_registry(
    registry: Mapping[str, Mapping[str, object]] | None = None,
) -> list[str]:
    source = registry if registry is not None else {
        action_id: action.to_dict() for action_id, action in FEDERATION_TYPED_ACTION_REGISTRY.items()
    }
    errors: list[str] = []
    for action_id, payload in source.items():
        if not isinstance(payload, Mapping):
            errors.append(f"invalid_mapping:{action_id}")
            continue
        resolved = str(payload.get("action_id") or "")
        if not resolved or resolved != action_id:
            errors.append(f"action_id_mismatch:{action_id}")
        for field in (
            "intent",
            "mutation_control_domain",
            "authority_class",
            "lifecycle_context",
            "canonical_entry_surface",
            "proof_visible_boundary",
        ):
            if not str(payload.get(field) or "").strip():
                errors.append(f"missing_{field}:{action_id}")
    return errors


__all__ = [
    "FEDERATION_TYPED_ACTIONS",
    "FEDERATION_TYPED_ACTION_REGISTRY",
    "federation_typed_action_diagnostic",
    "resolve_federation_typed_action_id",
    "validate_federation_typed_action_registry",
]
