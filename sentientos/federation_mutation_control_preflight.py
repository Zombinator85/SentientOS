from __future__ import annotations

from typing import Any, Mapping

from sentientos.constitutional_slice_pattern import non_sovereign_diagnostic_boundaries
from sentientos.federation_typed_actions import federation_typed_action_diagnostic


REQUIRED_READINESS_LAYERS: tuple[str, ...] = (
    "typed_action_model",
    "canonical_router_handler_viability",
    "success_denial_admitted_failure_clarity",
    "proof_visible_artifact_boundaries",
    "trace_requirements",
    "diagnostic_layer_prerequisites",
    "authority_of_judgment_clarity",
    "non_sovereign_boundary_compatibility",
)


DEFAULT_REQUIRED_LAYER_CLASSIFICATION: dict[str, str] = {
    "typed_action_model": "present",
    "canonical_router_handler_viability": "partially_present",
    "success_denial_admitted_failure_clarity": "partially_present",
    "proof_visible_artifact_boundaries": "partially_present",
    "trace_requirements": "present",
    "diagnostic_layer_prerequisites": "present",
    "authority_of_judgment_clarity": "present",
    "non_sovereign_boundary_compatibility": "present",
}


def _normalize_classification(value: object) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "_")
    allowed = {"present", "partially_present", "missing", "blocked_by_deeper_ambiguity"}
    if normalized in allowed:
        return normalized
    return "missing"


def _resolve_required_layer_classification(
    fixture: Mapping[str, object] | None,
) -> dict[str, str]:
    resolved = dict(DEFAULT_REQUIRED_LAYER_CLASSIFICATION)
    if fixture is None:
        return resolved
    candidate = fixture.get("required_layer_classification")
    if not isinstance(candidate, Mapping):
        return resolved
    for layer in REQUIRED_READINESS_LAYERS:
        if layer in candidate:
            resolved[layer] = _normalize_classification(candidate.get(layer))
    return resolved


def _readiness_verdict(required_layers: Mapping[str, str], blocker: str) -> str:
    if blocker:
        missing_count = sum(1 for value in required_layers.values() if value in {"missing", "blocked_by_deeper_ambiguity"})
        if missing_count <= 1:
            return "nearly_ready_blocked_by_one_major_prerequisite"
        return "not_yet_ready_too_many_foundational_gaps"
    if any(value in {"missing", "blocked_by_deeper_ambiguity"} for value in required_layers.values()):
        return "not_yet_ready_too_many_foundational_gaps"
    return "ready_for_initial_slice_onboarding"


def build_federation_mutation_control_preflight(
    fixture: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Diagnostic-only preflight for federation constitutional onboarding readiness."""

    required_layers = _resolve_required_layer_classification(fixture)
    blocker = "typed_action_model" if required_layers.get("typed_action_model") != "present" else ""
    typed_action_diag = federation_typed_action_diagnostic()

    return {
        "slice_id": "federation_mutation_control_slice",
        "candidate_slice_boundary": {
            "capability": "mutation_and_control",
            "candidate_action_intents": [
                "federation.restart_daemon_request",
                "federation.governance_digest_or_quorum_denial",
                "federation.epoch_or_trust_posture_gate",
            ],
            "candidate_canonical_entry_surfaces": [
                "sentientos.daemons.pulse_federation.ingest_remote_event",
                "sentientos.control_plane_kernel.ControlPlaneKernel.admit(authority_class=FEDERATED_CONTROL)",
                "sentientos.runtime_governor.RuntimeGovernor.admit_federated_control",
                "sentientos.federated_governance.FederatedGovernanceController.evaluate_peer_event",
            ],
            "proof_visible_artifact_event_boundaries": [
                "glow/control_plane/kernel_decisions.jsonl:event_type=control_plane_decision",
                "glow/governor/decisions.jsonl:event_type=governor_decision",
                "glow/federation/quorum_decisions.jsonl",
                "glow/federation/federation_ingest_log.jsonl",
            ],
            "initial_out_of_scope": [
                "federation envelope serialization/transport internals",
                "non-control federation summary/report generation",
                "cross-node replay synthesis beyond control admission decisions",
                "new governance authorities or sovereign layers",
            ],
        },
        "federation_surface_map": [
            {
                "surface": "pulse_federation.ingest_remote_event",
                "direction": "inbound_control",
                "canonical_slice_component_like": True,
                "typed_action_identity": "missing",
                "canonical_handler_boundary": "partially_present",
                "proof_visible_artifact_linkage": "partially_present",
                "denial_failure_semantics": "present",
                "authority_of_judgment_semantics": "partially_present",
            },
            {
                "surface": "control_plane_kernel.admit(FEDERATED_CONTROL)",
                "direction": "inbound_control",
                "canonical_slice_component_like": True,
                "typed_action_identity": "missing",
                "canonical_handler_boundary": "present",
                "proof_visible_artifact_linkage": "present",
                "denial_failure_semantics": "present",
                "authority_of_judgment_semantics": "present",
            },
            {
                "surface": "runtime_governor.admit_federated_control",
                "direction": "control_mediation",
                "canonical_slice_component_like": True,
                "typed_action_identity": "missing",
                "canonical_handler_boundary": "present",
                "proof_visible_artifact_linkage": "present",
                "denial_failure_semantics": "present",
                "authority_of_judgment_semantics": "present",
            },
            {
                "surface": "federated_governance.evaluate_peer_event",
                "direction": "outbound_control_mutation",
                "canonical_slice_component_like": True,
                "typed_action_identity": "missing",
                "canonical_handler_boundary": "partially_present",
                "proof_visible_artifact_linkage": "partially_present",
                "denial_failure_semantics": "present",
                "authority_of_judgment_semantics": "partially_present",
            },
            {
                "surface": "federation.enablement.legacy_federation_bypass",
                "direction": "bypass_like_helper",
                "canonical_slice_component_like": False,
                "typed_action_identity": "missing",
                "canonical_handler_boundary": "missing",
                "proof_visible_artifact_linkage": "missing",
                "denial_failure_semantics": "missing",
                "authority_of_judgment_semantics": "missing",
            },
        ],
        "required_layer_comparison": required_layers,
        "single_most_important_blocking_prerequisite": {
            "requirement": blocker or "none",
            "why": "federation control intents are currently inferred from event payload fields/reason codes, not from a stable typed action catalog bound one-to-one with canonical handlers.",
        },
        "readiness_verdict": _readiness_verdict(required_layers, blocker),
        "typed_onboarding_pass_note": {
            "chosen_for_initial_typed_onboarding": [row["intent"] for row in typed_action_diag["chosen_intents"]],
            "remaining_out_of_scope": list(typed_action_diag["untyped_out_of_scope_intents"]),
            "scope_statement": "typed identity registration and emission only; no full federation router migration in this pass",
            "cleared_prerequisite": "typed_action_model",
            "next_prerequisite_unlocked": "future router/provenance onboarding can bind canonical execution linkage to stable typed federation action IDs",
        },
        "recommended_next_move_before_onboarding": (
            "typed identity baseline is established for a bounded federation control subset; "
            "next move is canonical router/provenance linkage for this same bounded subset without widening scope."
        ),
        "typed_action_diagnostic": typed_action_diag,
        "non_sovereign_boundaries": non_sovereign_diagnostic_boundaries(
            derived_from=[
                "sentientos.daemons.pulse_federation",
                "sentientos.control_plane_kernel",
                "sentientos.runtime_governor",
                "sentientos.federated_governance",
            ],
            extra={"new_authority": False, "automatic_execution": False, "audit_only": True},
        ),
    }


__all__ = [
    "REQUIRED_READINESS_LAYERS",
    "build_federation_mutation_control_preflight",
]
