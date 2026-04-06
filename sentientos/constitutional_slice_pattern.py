from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


REQUIRED_PATTERN_LAYERS: tuple[str, ...] = (
    "typed_mutation_action",
    "canonical_router_handler_registration",
    "canonical_success_denial_admitted_failure_semantics",
    "scoped_trace_coherence_evaluation",
    "lifecycle_resolution",
    "slice_health_synthesis",
    "temporal_health_history",
    "stability_oscillation_diagnostics",
    "retrospective_integrity_review",
    "operator_attention_recommendation",
)

OPTIONAL_ADVANCED_PATTERN_LAYERS: tuple[str, ...] = (
    "explicit_proof_visible_artifact_boundaries",
    "corridor_surface_mapping",
    "trust_surface_mapping",
    "bounded_history_retention_policy",
)

CURRENT_SLICE_SPECIFIC_LAYERS: tuple[str, ...] = (
    "seven_action_catalog",
    "current_action_specific_side_effect_resolvers",
)


def non_sovereign_diagnostic_boundaries(*, derived_from: str | list[str], extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Canonical bounded non-sovereign envelope for scoped diagnostic outputs."""

    payload: dict[str, Any] = {
        "diagnostic_only": True,
        "non_authoritative": True,
        "decision_power": "none",
        "does_not_block_mutations": True,
        "does_not_override_kernel_or_governor": True,
        "does_not_replace_corridor_proof": True,
        "does_not_replace_jurisprudence": True,
        "derived_from": derived_from,
    }
    if extra:
        payload.update(dict(extra))
    return payload


@dataclass(frozen=True, slots=True)
class ConstitutionalizedSliceScaffold:
    """Compact machine-readable onboarding scaffold for one constitutionalized slice."""

    slice_id: str
    action_ids: tuple[str, ...]
    canonical_handlers: dict[str, str]
    proof_visible_artifact_boundaries: dict[str, tuple[str, ...]]
    trace_requirements: dict[str, Any]
    success_denial_failure_expectations: dict[str, Any]
    diagnostic_capabilities_enabled: dict[str, bool]
    required_layers: tuple[str, ...] = REQUIRED_PATTERN_LAYERS
    optional_advanced_layers: tuple[str, ...] = OPTIONAL_ADVANCED_PATTERN_LAYERS
    current_slice_specific_layers: tuple[str, ...] = CURRENT_SLICE_SPECIFIC_LAYERS

    def to_dict(self) -> dict[str, Any]:
        return {
            "slice_id": self.slice_id,
            "action_ids": list(self.action_ids),
            "canonical_handlers": dict(self.canonical_handlers),
            "proof_visible_artifact_boundaries": {key: list(value) for key, value in self.proof_visible_artifact_boundaries.items()},
            "trace_requirements": dict(self.trace_requirements),
            "success_denial_failure_expectations": dict(self.success_denial_failure_expectations),
            "diagnostic_capabilities_enabled": dict(self.diagnostic_capabilities_enabled),
            "required_layers": list(self.required_layers),
            "optional_advanced_layers": list(self.optional_advanced_layers),
            "current_slice_specific_layers": list(self.current_slice_specific_layers),
        }


def build_current_slice_pattern_scaffold() -> ConstitutionalizedSliceScaffold:
    action_ids = (
        "sentientos.manifest.generate",
        "sentientos.quarantine.clear",
        "sentientos.genesis.lineage_integrate",
        "sentientos.genesis.proposal_adopt",
        "sentientos.codexhealer.repair",
        "sentientos.merge_train.hold",
        "sentientos.merge_train.release",
    )
    return ConstitutionalizedSliceScaffold(
        slice_id="constitutional_execution_fabric_scoped_slice",
        action_ids=action_ids,
        canonical_handlers={
            "sentientos.manifest.generate": "scripts.generate_immutable_manifest.generate_manifest",
            "sentientos.quarantine.clear": "sentientos.integrity_quarantine.clear",
            "sentientos.genesis.lineage_integrate": "sentientos.genesis_forge.SpecBinder.integrate",
            "sentientos.genesis.proposal_adopt": "sentientos.genesis_forge.AdoptionRite.promote",
            "sentientos.codexhealer.repair": "sentientos.codex_healer.RepairSynthesizer.apply",
            "sentientos.merge_train.hold": "sentientos.forge_merge_train.ForgeMergeTrain._apply_hold_transition",
            "sentientos.merge_train.release": "sentientos.forge_merge_train.ForgeMergeTrain._apply_release_transition",
        },
        proof_visible_artifact_boundaries={
            "sentientos.manifest.generate": ("vow/immutable_manifest.json:admission",),
            "sentientos.quarantine.clear": ("pulse/forge_events.jsonl:event=integrity_recovered",),
            "sentientos.genesis.lineage_integrate": ("lineage/lineage.jsonl",),
            "sentientos.genesis.proposal_adopt": ("live/*.json:admission", "codex.json:admission"),
            "sentientos.codexhealer.repair": (
                "integration/healer_runtime.log.jsonl:canonical_admission",
                "integration/healer_runtime.log.jsonl:details.kernel_admission",
            ),
            "sentientos.merge_train.hold": ("pulse/forge_train_events.jsonl:event=train_held",),
            "sentientos.merge_train.release": ("pulse/forge_train_events.jsonl:event=train_released",),
        },
        trace_requirements={
            "router_event": "pulse/forge_events.jsonl:event=constitutional_mutation_router_execution",
            "kernel_admission": "glow/control_plane/kernel_decisions.jsonl:event_type=control_plane_decision",
            "required_linkage_fields": ["typed_action_id", "correlation_id", "admission_decision_ref"],
            "path_status": "canonical_router",
        },
        success_denial_failure_expectations={
            "success": {"final_disposition": "allow", "execution_status": "succeeded", "side_effect_state": "present"},
            "denied": {"final_disposition": "deny", "execution_status": "denied", "side_effect_state": "absent"},
            "failed_after_admission": {
                "final_disposition": "allow",
                "execution_status": "failed",
                "partial_side_effect_state": "unknown_partial_side_effects_possible",
            },
            "fragmented_unresolved": {"missing_any": ["router_event", "kernel_admission", "proof_linkage"]},
        },
        diagnostic_capabilities_enabled={
            "scoped_trace_coherence_evaluation": True,
            "lifecycle_resolution": True,
            "slice_health_synthesis": True,
            "temporal_health_history": True,
            "stability_oscillation_diagnostics": True,
            "retrospective_integrity_review": True,
            "operator_attention_recommendation": True,
            "new_authority": False,
            "automatic_execution": False,
        },
    )


def validate_slice_pattern_scaffold(payload: Mapping[str, Any]) -> list[str]:
    """Return validation errors; empty list means internally coherent scaffold."""

    errors: list[str] = []
    required_top_level = (
        "slice_id",
        "action_ids",
        "canonical_handlers",
        "proof_visible_artifact_boundaries",
        "trace_requirements",
        "success_denial_failure_expectations",
        "diagnostic_capabilities_enabled",
        "required_layers",
    )
    for key in required_top_level:
        if key not in payload:
            errors.append(f"missing_required_field:{key}")

    action_ids = payload.get("action_ids")
    if isinstance(action_ids, list):
        for action_id in action_ids:
            if not isinstance(action_id, str) or not action_id:
                errors.append("invalid_action_id")
    else:
        errors.append("invalid_action_ids")
        action_ids = []

    handlers = payload.get("canonical_handlers")
    if isinstance(handlers, Mapping):
        for action_id in action_ids:
            if action_id not in handlers:
                errors.append(f"missing_canonical_handler:{action_id}")
    else:
        errors.append("invalid_canonical_handlers")

    required_layers = payload.get("required_layers")
    if isinstance(required_layers, list):
        missing_layers = [layer for layer in REQUIRED_PATTERN_LAYERS if layer not in required_layers]
        for layer in missing_layers:
            errors.append(f"missing_required_layer:{layer}")
    else:
        errors.append("invalid_required_layers")

    capabilities = payload.get("diagnostic_capabilities_enabled")
    if not isinstance(capabilities, Mapping):
        errors.append("invalid_diagnostic_capabilities")
    else:
        if capabilities.get("new_authority") is True:
            errors.append("invalid_capability:new_authority_must_remain_false")
        if capabilities.get("automatic_execution") is True:
            errors.append("invalid_capability:automatic_execution_must_remain_false")

    return errors


def slice_pattern_onboarding_note() -> dict[str, Any]:
    """Compact developer/operator-facing onboarding note for the next slice."""

    return {
        "pattern_summary": {
            "execution_substrate": [
                "TypedMutationAction + canonical router admission path",
                "action registration with canonical handler identity",
            ],
            "trace_model": [
                "router execution event",
                "kernel admission decision",
                "action-scoped proof-visible side effect boundary",
            ],
            "diagnostic_stack": [
                "lifecycle resolution",
                "slice health",
                "temporal history",
                "stability / oscillation",
                "retrospective integrity review",
                "bounded operator attention recommendation",
            ],
        },
        "reusable_now": {
            "required_layers": list(REQUIRED_PATTERN_LAYERS),
            "optional_advanced_layers": list(OPTIONAL_ADVANCED_PATTERN_LAYERS),
            "current_slice_specific_layers": list(CURRENT_SLICE_SPECIFIC_LAYERS),
        },
        "onboard_new_slice": [
            "define typed action IDs and canonical handlers",
            "declare proof-visible artifact boundaries per action",
            "wire lifecycle resolver over scoped actions only",
            "reuse non-sovereign diagnostic boundaries and classify outcomes",
            "enable history/stability/retrospective/attention only as diagnostic support",
        ],
        "do_not_do": [
            "do not universalize to whole-repo governance",
            "do not introduce new authority or autonomous execution via scaffold",
            "do not replace kernel, governor, corridor proofs, or jurisprudence",
            "do not add unrelated diagnostics in this extraction pass",
        ],
        "recommended_next_slice_candidate": {
            "slice_id": "federation_mutation_control_slice",
            "why_best_next": "federation actions already have explicit trust/log surfaces and bounded mutation domains, so they fit the same admission+trace+diagnostic shape.",
            "existing_prerequisites": [
                "federation trust protocol log surfaces",
                "control-plane admission path and authority classes",
                "protected mutation corridor conventions",
            ],
            "biggest_missing_prerequisites": [
                "typed federation action catalog bound to canonical handlers",
                "explicit proof-visible side-effect linkage assertions for each federation action",
                "slice-local lifecycle resolver equivalent to current seven-action resolver",
            ],
            "relative_difficulty_vs_current_slice": "harder_than_current_slice_due_to_cross-node_side_effects_and_multi_surface_proof_linkage",
        },
    }
