from __future__ import annotations

import json

from sentientos.federation_slice_pattern import (
    OPTIONAL_ADVANCED_FEDERATION_PATTERN_LAYERS,
    REQUIRED_FEDERATION_PATTERN_LAYERS,
    bounded_federation_slice_onboarding_note,
    build_post_expansion_bounded_federation_coherence_artifact,
    build_bounded_federation_seed_scaffold,
    validate_federation_slice_scaffold,
)


def test_bounded_federation_seed_scaffold_is_coherent() -> None:
    scaffold = build_bounded_federation_seed_scaffold().to_dict()

    errors = validate_federation_slice_scaffold(scaffold)

    assert errors == [], json.dumps(errors, indent=2)


def test_required_and_optional_layer_buckets_are_distinct() -> None:
    scaffold = build_bounded_federation_seed_scaffold().to_dict()
    layers = scaffold["layer_classification"]

    required = set(layers["required_for_new_bounded_slice"])
    optional = set(layers["optional_or_advanced"])

    assert set(REQUIRED_FEDERATION_PATTERN_LAYERS).issubset(required)
    assert set(OPTIONAL_ADVANCED_FEDERATION_PATTERN_LAYERS).issubset(optional)
    assert required.isdisjoint(optional)


def test_missing_required_fields_and_layers_are_detectable() -> None:
    scaffold = build_bounded_federation_seed_scaffold().to_dict()
    scaffold.pop("slice_id")
    scaffold["layer_classification"]["required_for_new_bounded_slice"] = [
        layer
        for layer in scaffold["layer_classification"]["required_for_new_bounded_slice"]
        if layer != "bounded_lifecycle_resolution"
    ]

    errors = validate_federation_slice_scaffold(scaffold)

    assert "missing_required_field:slice_id" in errors
    assert "missing_required_layer:bounded_lifecycle_resolution" in errors


def test_scaffold_cannot_introduce_authority_or_execution_behavior() -> None:
    scaffold = build_bounded_federation_seed_scaffold().to_dict()
    capabilities = dict(scaffold["diagnostic_capabilities_enabled"])
    capabilities["new_authority"] = True
    capabilities["automatic_execution"] = True
    scaffold["diagnostic_capabilities_enabled"] = capabilities

    errors = validate_federation_slice_scaffold(scaffold)

    assert "invalid_capability:new_authority_must_remain_false" in errors
    assert "invalid_capability:automatic_execution_must_remain_false" in errors


def test_note_captures_reusable_pattern_and_next_candidate_without_rollout() -> None:
    note = bounded_federation_slice_onboarding_note()

    assert "pattern" in note
    assert "reusable_layers" in note
    assert "next_onboarding_steps" in note
    assert "do_not_do" in note

    candidate = note["recommended_next_bounded_candidate"]
    assert candidate["relative_difficulty"].startswith("slightly_harder")
    assert note["onboarded_increment"]["status"] == "implemented_bounded_increment_v1"
    post_expansion = note["post_expansion_coherence"]
    assert "federation.replay_or_receipt_consistency_gate" in post_expansion["current_in_scope_intent_ids"]
    assert post_expansion["slice_coherence_assessment"] == "remains_one_bounded_constitutional_subsystem"
    assert post_expansion["next_move_recommendation"] == "consolidation_first_before_next_increment"


def test_post_expansion_coherence_artifact_reports_bounded_in_scope_and_non_authority() -> None:
    artifact = build_post_expansion_bounded_federation_coherence_artifact()
    assert artifact["artifact_kind"] == "bounded_federation_post_expansion_coherence_audit"
    assert artifact["in_scope_intent_count"] == 5
    assert artifact["coherence_verdict"] == "coherent_bounded_constitutional_subsystem"
    assert artifact["maturity_counts"]["fully_integrated"] == 5
    assert artifact["diagnostic_only"] is True
    assert artifact["non_authoritative"] is True
    assert artifact["decision_power"] == "none"
    assert artifact["does_not_create_new_authority"] is True
    assert artifact["acts_as_federation_adjudicator"] is False


def test_post_expansion_coherence_artifact_detects_uneven_integration_when_typed_identity_drifts(monkeypatch) -> None:
    from sentientos import federation_slice_pattern as fsp

    registry = dict(fsp.FEDERATION_TYPED_ACTION_REGISTRY)
    drifted = registry["sentientos.federation.governance_digest_or_quorum_denial_gate"]
    monkeypatch.setattr(
        fsp,
        "FEDERATION_TYPED_ACTION_REGISTRY",
        {
            **registry,
            "sentientos.federation.governance_digest_or_quorum_denial_gate": drifted.__class__(  # type: ignore[misc]
                action_id=drifted.action_id,
                intent="federation.governance_digest_or_quorum_denial",
                mutation_control_domain=drifted.mutation_control_domain,
                authority_class=drifted.authority_class,
                lifecycle_context=drifted.lifecycle_context,
                canonical_entry_surface=drifted.canonical_entry_surface,
                proof_visible_boundary=drifted.proof_visible_boundary,
            ),
        },
    )

    artifact = build_post_expansion_bounded_federation_coherence_artifact()
    assert artifact["coherence_verdict"] == "fragmenting_or_uneven_sub_slices_detected"
    assert artifact["maturity_counts"]["mostly_integrated"] == 1
