from __future__ import annotations

import json

from sentientos.federation_slice_pattern import (
    OPTIONAL_ADVANCED_FEDERATION_PATTERN_LAYERS,
    REQUIRED_FEDERATION_PATTERN_LAYERS,
    bounded_federation_slice_onboarding_note,
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
