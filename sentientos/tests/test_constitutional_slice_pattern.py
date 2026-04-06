from __future__ import annotations

import json

from sentientos.constitutional_slice_pattern import (
    OPTIONAL_ADVANCED_PATTERN_LAYERS,
    REQUIRED_PATTERN_LAYERS,
    build_current_slice_pattern_scaffold,
    slice_pattern_onboarding_note,
    validate_slice_pattern_scaffold,
)


def test_current_scaffold_is_internally_coherent() -> None:
    scaffold = build_current_slice_pattern_scaffold().to_dict()

    errors = validate_slice_pattern_scaffold(scaffold)
    assert errors == [], json.dumps(errors, indent=2)


def test_scaffold_distinguishes_required_and_optional_layers() -> None:
    scaffold = build_current_slice_pattern_scaffold().to_dict()
    required = set(scaffold["required_layers"])
    optional = set(scaffold["optional_advanced_layers"])

    assert set(REQUIRED_PATTERN_LAYERS).issubset(required)
    assert set(OPTIONAL_ADVANCED_PATTERN_LAYERS).issubset(optional)
    assert required.isdisjoint(optional)


def test_scaffold_missing_required_elements_is_detectable() -> None:
    scaffold = build_current_slice_pattern_scaffold().to_dict()
    scaffold.pop("slice_id")
    scaffold["required_layers"] = [layer for layer in scaffold["required_layers"] if layer != "lifecycle_resolution"]

    errors = validate_slice_pattern_scaffold(scaffold)

    assert "missing_required_field:slice_id" in errors
    assert "missing_required_layer:lifecycle_resolution" in errors


def test_scaffold_does_not_allow_authority_or_execution_escalation() -> None:
    scaffold = build_current_slice_pattern_scaffold().to_dict()
    capabilities = dict(scaffold["diagnostic_capabilities_enabled"])
    capabilities["new_authority"] = True
    capabilities["automatic_execution"] = True
    scaffold["diagnostic_capabilities_enabled"] = capabilities

    errors = validate_slice_pattern_scaffold(scaffold)

    assert "invalid_capability:new_authority_must_remain_false" in errors
    assert "invalid_capability:automatic_execution_must_remain_false" in errors


def test_onboarding_note_is_compact_and_actionable() -> None:
    note = slice_pattern_onboarding_note()

    assert "pattern_summary" in note
    assert "reusable_now" in note
    assert "onboard_new_slice" in note
    assert "do_not_do" in note
    candidate = note["recommended_next_slice_candidate"]
    assert candidate["slice_id"] == "federation_mutation_control_slice"
    assert "harder_than_current_slice" in candidate["relative_difficulty_vs_current_slice"]
