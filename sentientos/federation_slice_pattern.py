from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


REQUIRED_FEDERATION_PATTERN_LAYERS: tuple[str, ...] = (
    "typed_federation_action_identity",
    "bounded_canonical_execution_path",
    "explicit_success_denial_admitted_failure_semantics",
    "proof_visible_execution_history",
    "bounded_lifecycle_resolution",
    "bounded_health_synthesis",
    "bounded_temporal_health_history",
    "bounded_stability_oscillation_diagnostics",
    "bounded_retrospective_integrity_review",
    "bounded_operator_attention_recommendation",
)

OPTIONAL_ADVANCED_FEDERATION_PATTERN_LAYERS: tuple[str, ...] = (
    "cross_surface_artifact_redundancy_checks",
    "bounded_history_retention_policy",
)

CURRENT_SEED_SPECIFIC_FEDERATION_PATTERN_LAYERS: tuple[str, ...] = (
    "restart_daemon_request_intent",
    "governance_digest_or_quorum_denial_gate_intent",
    "epoch_or_trust_posture_gate_intent",
)


def build_bounded_diagnostic_capability_flags() -> dict[str, bool]:
    """Return the bounded non-sovereign diagnostic capability map for a slice scaffold."""

    return {
        "bounded_lifecycle_resolution": True,
        "bounded_health_synthesis": True,
        "bounded_temporal_health_history": True,
        "bounded_stability_oscillation_diagnostics": True,
        "bounded_retrospective_integrity_review": True,
        "bounded_operator_attention_recommendation": True,
        "new_authority": False,
        "automatic_execution": False,
        "governance_layer_introduced": False,
        "new_sovereign_introduced": False,
    }


@dataclass(frozen=True, slots=True)
class FederationSliceScaffold:
    slice_id: str
    in_scope_intent_ids: tuple[str, ...]
    typed_action_ids: tuple[str, ...]
    canonical_ingress_surfaces: tuple[str, ...]
    canonical_handlers: dict[str, str]
    proof_visible_artifact_boundaries: dict[str, tuple[str, ...]]
    lifecycle_trace_requirements: dict[str, Any]
    diagnostic_capabilities_enabled: dict[str, bool]
    success_denial_admitted_failure_expectations: dict[str, Any]
    layer_classification: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "slice_id": self.slice_id,
            "in_scope_intent_ids": list(self.in_scope_intent_ids),
            "typed_action_ids": list(self.typed_action_ids),
            "canonical_ingress_surfaces": list(self.canonical_ingress_surfaces),
            "canonical_handlers": dict(self.canonical_handlers),
            "proof_visible_artifact_boundaries": {
                key: list(value) for key, value in self.proof_visible_artifact_boundaries.items()
            },
            "lifecycle_trace_requirements": dict(self.lifecycle_trace_requirements),
            "diagnostic_capabilities_enabled": dict(self.diagnostic_capabilities_enabled),
            "success_denial_admitted_failure_expectations": dict(self.success_denial_admitted_failure_expectations),
            "layer_classification": {
                key: list(value) for key, value in self.layer_classification.items()
            },
        }


def build_bounded_federation_seed_scaffold() -> FederationSliceScaffold:
    """Build a compact reusable scaffold from the currently onboarded bounded federation seed only."""

    typed_action_ids = (
        "sentientos.federation.restart_daemon_request",
        "sentientos.federation.governance_digest_or_quorum_denial_gate",
        "sentientos.federation.epoch_or_trust_posture_gate",
    )
    return FederationSliceScaffold(
        slice_id="bounded_federation_seed",
        in_scope_intent_ids=(
            "federation.restart_daemon_request",
            "federation.governance_digest_or_quorum_denial_gate",
            "federation.epoch_or_trust_posture_gate",
        ),
        typed_action_ids=typed_action_ids,
        canonical_ingress_surfaces=(
            "sentientos.daemons.pulse_federation.ingest_remote_event",
            "sentientos.control_plane_kernel.ControlPlaneKernel.admit(authority_class=FEDERATED_CONTROL)",
        ),
        canonical_handlers={
            "sentientos.federation.restart_daemon_request": "sentientos.daemons.pulse_federation._canonical_restart_daemon_handler.v1",
            "sentientos.federation.governance_digest_or_quorum_denial_gate": "sentientos.daemons.pulse_federation._canonical_governance_gate_handler.v1",
            "sentientos.federation.epoch_or_trust_posture_gate": "sentientos.daemons.pulse_federation._canonical_epoch_trust_gate_handler.v1",
        },
        proof_visible_artifact_boundaries={
            "sentientos.federation.restart_daemon_request": (
                "glow/federation/ingest_classifications.jsonl:event_type+typed_action_id",
                "glow/federation/canonical_execution.jsonl:canonical_handler+admission_decision_ref",
            ),
            "sentientos.federation.governance_digest_or_quorum_denial_gate": (
                "glow/control_plane/kernel_decisions.jsonl:reason_codes+delegated_outcomes",
                "glow/federation/canonical_execution.jsonl:canonical_handler+admission_decision_ref",
            ),
            "sentientos.federation.epoch_or_trust_posture_gate": (
                "glow/control_plane/kernel_decisions.jsonl:reason_codes+delegated_outcomes.federation_context",
                "glow/federation/canonical_execution.jsonl:canonical_handler+admission_decision_ref",
            ),
        },
        lifecycle_trace_requirements={
            "canonical_execution_log": "glow/federation/canonical_execution.jsonl",
            "ingress_classification_log": "glow/federation/ingest_classifications.jsonl",
            "required_linkage_fields": [
                "typed_action_id",
                "correlation_id",
                "admission_decision_ref",
                "canonical_handler",
            ],
            "bounded_lifecycle_resolver": "sentientos.federation_bounded_lifecycle.resolve_bounded_federation_lifecycle",
            "proof_visible_join_rule": "correlation_id+typed_action_id join between ingress_classifications and canonical_execution",
        },
        diagnostic_capabilities_enabled=build_bounded_diagnostic_capability_flags(),
        success_denial_admitted_failure_expectations={
            "success": {
                "canonical_outcome": "admitted_succeeded",
                "admission_disposition": "admitted",
                "outcome_class": "success",
                "side_effect_semantics": ["side_effect_committed", "no_side_effect"],
            },
            "denial": {
                "canonical_outcome": "denied_pre_execution",
                "admission_disposition": "denied",
                "outcome_class": "denied",
                "side_effect_semantics": ["no_side_effect"],
            },
            "admitted_failure": {
                "canonical_outcome": "admitted_failed",
                "admission_disposition": "admitted",
                "outcome_class": "failed_after_admission",
                "failure_payload_required": True,
                "side_effect_semantics": ["unknown_partial_side_effects_possible"],
            },
            "fragmented_unresolved": {
                "outcome_class": "fragmented_unresolved",
                "missing_any": ["canonical_execution", "ingress_classification", "proof_linkage"],
            },
        },
        layer_classification={
            "required_for_new_bounded_slice": REQUIRED_FEDERATION_PATTERN_LAYERS,
            "optional_or_advanced": OPTIONAL_ADVANCED_FEDERATION_PATTERN_LAYERS,
            "specific_to_current_seed": CURRENT_SEED_SPECIFIC_FEDERATION_PATTERN_LAYERS,
        },
    )


def validate_federation_slice_scaffold(payload: Mapping[str, Any]) -> list[str]:
    """Return validation errors; empty list means scaffold is coherent and non-sovereign."""

    errors: list[str] = []
    required_top_level = (
        "slice_id",
        "in_scope_intent_ids",
        "typed_action_ids",
        "canonical_ingress_surfaces",
        "canonical_handlers",
        "proof_visible_artifact_boundaries",
        "lifecycle_trace_requirements",
        "diagnostic_capabilities_enabled",
        "success_denial_admitted_failure_expectations",
        "layer_classification",
    )
    for key in required_top_level:
        if key not in payload:
            errors.append(f"missing_required_field:{key}")

    typed_action_ids = payload.get("typed_action_ids")
    if not isinstance(typed_action_ids, list) or not typed_action_ids:
        errors.append("invalid_typed_action_ids")
        typed_action_ids = []

    handlers = payload.get("canonical_handlers")
    if not isinstance(handlers, Mapping):
        errors.append("invalid_canonical_handlers")
        handlers = {}
    for action_id in typed_action_ids:
        if action_id not in handlers:
            errors.append(f"missing_canonical_handler:{action_id}")

    boundaries = payload.get("proof_visible_artifact_boundaries")
    if not isinstance(boundaries, Mapping):
        errors.append("invalid_proof_visible_artifact_boundaries")
        boundaries = {}
    for action_id in typed_action_ids:
        if action_id not in boundaries:
            errors.append(f"missing_proof_visible_boundary:{action_id}")

    layer_classification = payload.get("layer_classification")
    if not isinstance(layer_classification, Mapping):
        errors.append("invalid_layer_classification")
    else:
        required = layer_classification.get("required_for_new_bounded_slice")
        optional = layer_classification.get("optional_or_advanced")
        specific = layer_classification.get("specific_to_current_seed")
        if not isinstance(required, list):
            errors.append("invalid_required_layer_bucket")
            required = []
        if not isinstance(optional, list):
            errors.append("invalid_optional_layer_bucket")
            optional = []
        if not isinstance(specific, list):
            errors.append("invalid_seed_specific_layer_bucket")
            specific = []

        for layer in REQUIRED_FEDERATION_PATTERN_LAYERS:
            if layer not in required:
                errors.append(f"missing_required_layer:{layer}")
        if set(required) & set(optional):
            errors.append("layer_overlap:required_optional")
        if set(required) & set(specific):
            errors.append("layer_overlap:required_seed_specific")

    capabilities = payload.get("diagnostic_capabilities_enabled")
    if not isinstance(capabilities, Mapping):
        errors.append("invalid_diagnostic_capabilities")
    else:
        forbidden_true = (
            "new_authority",
            "automatic_execution",
            "governance_layer_introduced",
            "new_sovereign_introduced",
        )
        for field in forbidden_true:
            if capabilities.get(field) is True:
                errors.append(f"invalid_capability:{field}_must_remain_false")

    expectations = payload.get("success_denial_admitted_failure_expectations")
    if not isinstance(expectations, Mapping):
        errors.append("invalid_success_denial_admitted_failure_expectations")
    else:
        for field in ("success", "denial", "admitted_failure"):
            if field not in expectations:
                errors.append(f"missing_expectation:{field}")

    return errors


def bounded_federation_slice_onboarding_note() -> dict[str, Any]:
    """Compact developer/operator note for onboarding the next bounded federation sub-slice."""

    return {
        "pattern": {
            "execution_substrate": "typed federation action identity + bounded canonical execution router",
            "trace_model": "proof-visible correlation between ingress classification and canonical execution",
            "diagnostic_stack": [
                "lifecycle resolution",
                "health synthesis",
                "temporal history",
                "stability/oscillation",
                "retrospective integrity",
                "operator attention recommendation",
            ],
        },
        "reusable_layers": {
            "required": list(REQUIRED_FEDERATION_PATTERN_LAYERS),
            "optional": list(OPTIONAL_ADVANCED_FEDERATION_PATTERN_LAYERS),
            "seed_specific": list(CURRENT_SEED_SPECIFIC_FEDERATION_PATTERN_LAYERS),
        },
        "next_onboarding_steps": [
            "define typed action IDs and in-scope intent IDs for the new bounded candidate",
            "bind each typed action to one canonical ingress and canonical handler",
            "declare proof-visible artifact boundaries per action",
            "reuse lifecycle+health+history+stability+retrospective+attention diagnostics without widening authority",
        ],
        "do_not_do": [
            "do not onboard out-of-scope intents in this pass",
            "do not introduce a new governance layer or sovereign",
            "do not convert scaffold into an auto-execution framework",
            "do not universalize federation constitutionalization across the whole repository",
        ],
        "recommended_next_bounded_candidate": {
            "intent_set": [
                "federation.replay_or_receipt_consistency_gate",
                "federation.ingest_replay_admission_gate",
            ],
            "why_best_next_increment": (
                "It extends the existing proof-visible lifecycle model without introducing new execution authority, "
                "and directly reuses correlation/admission linkage surfaces already present in canonical_execution and ingest logs."
            ),
            "already_has_prerequisites": [
                "typed action resolution path in pulse federation ingest",
                "canonical admission decision linkage fields",
                "bounded lifecycle and health diagnostics that already classify fragmented traces",
            ],
            "missing_prerequisites": [
                "typed action IDs for replay/receipt gate intents",
                "canonical handlers for replay/receipt gate outcomes",
                "explicit proof-visible boundary declarations for replay/receipt artifacts",
            ],
            "relative_difficulty": "slightly_harder_than_current_seed_due_to_multi_artifact_replay_coherence_checks",
        },
    }


__all__ = [
    "CURRENT_SEED_SPECIFIC_FEDERATION_PATTERN_LAYERS",
    "OPTIONAL_ADVANCED_FEDERATION_PATTERN_LAYERS",
    "REQUIRED_FEDERATION_PATTERN_LAYERS",
    "FederationSliceScaffold",
    "bounded_federation_slice_onboarding_note",
    "build_bounded_diagnostic_capability_flags",
    "build_bounded_federation_seed_scaffold",
    "validate_federation_slice_scaffold",
]
