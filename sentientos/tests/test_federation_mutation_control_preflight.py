from __future__ import annotations

from sentientos.federation_mutation_control_preflight import (
    REQUIRED_READINESS_LAYERS,
    build_federation_mutation_control_preflight,
)


def test_preflight_reports_required_layer_presence_and_absence() -> None:
    report = build_federation_mutation_control_preflight()
    required = report["required_layer_comparison"]

    assert set(REQUIRED_READINESS_LAYERS).issubset(required.keys())
    assert required["typed_action_model"] == "present"
    assert required["trace_requirements"] == "present"


def test_preflight_detects_single_critical_missing_prerequisite() -> None:
    report = build_federation_mutation_control_preflight()
    blocker = report["single_most_important_blocking_prerequisite"]

    assert blocker["requirement"] == "none"
    assert report["typed_onboarding_pass_note"]["cleared_prerequisite"] == "canonical_execution_seed_for_bounded_federation_intents"
    assert "canonical seed now exists" in report["recommended_next_move_before_onboarding"]
    assert "canonical_execution_diagnostic" in report
    assert "bounded_federation_lifecycle_diagnostic" in report


def test_readiness_verdict_changes_when_required_fields_change() -> None:
    not_ready = build_federation_mutation_control_preflight(
        {
            "required_layer_classification": {
                "typed_action_model": "missing",
                "canonical_router_handler_viability": "missing",
            }
        }
    )
    nearly_ready = build_federation_mutation_control_preflight(
        {
            "required_layer_classification": {
                "typed_action_model": "missing",
                "canonical_router_handler_viability": "present",
                "success_denial_admitted_failure_clarity": "present",
                "proof_visible_artifact_boundaries": "present",
                "trace_requirements": "present",
                "diagnostic_layer_prerequisites": "present",
                "authority_of_judgment_clarity": "present",
                "non_sovereign_boundary_compatibility": "present",
            }
        }
    )
    ready = build_federation_mutation_control_preflight(
        {
            "required_layer_classification": {
                "typed_action_model": "present",
                "canonical_router_handler_viability": "present",
                "success_denial_admitted_failure_clarity": "present",
                "proof_visible_artifact_boundaries": "present",
                "trace_requirements": "present",
                "diagnostic_layer_prerequisites": "present",
                "authority_of_judgment_clarity": "present",
                "non_sovereign_boundary_compatibility": "present",
            }
        }
    )

    assert not_ready["readiness_verdict"] == "not_yet_ready_too_many_foundational_gaps"
    assert nearly_ready["readiness_verdict"] == "nearly_ready_blocked_by_one_major_prerequisite"
    assert ready["readiness_verdict"] == "ready_for_initial_slice_onboarding"


def test_preflight_stays_non_sovereign_and_non_executing() -> None:
    report = build_federation_mutation_control_preflight()
    boundaries = report["non_sovereign_boundaries"]

    assert boundaries["diagnostic_only"] is True
    assert boundaries["non_authoritative"] is True
    assert boundaries["decision_power"] == "none"
    assert boundaries["new_authority"] is False
    assert boundaries["automatic_execution"] is False
