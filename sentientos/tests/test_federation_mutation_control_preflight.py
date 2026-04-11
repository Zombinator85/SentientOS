from __future__ import annotations

import pytest

from sentientos.federation_mutation_control_preflight import (
    REQUIRED_READINESS_LAYERS,
    build_federation_mutation_control_preflight,
)


@pytest.fixture(autouse=True)
def _isolate_preflight_history_artifacts(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)



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
    onboarding_note = report["typed_onboarding_pass_note"]["bounded_seed_health_note"]
    assert onboarding_note["statuses"] == ["healthy", "degraded", "fragmented"]
    assert "recovered_from_failure" in onboarding_note["transition_classes"]
    assert "does not widen the federation intent slice" in onboarding_note["does_not_do"]
    assert "support-only observability signal" in onboarding_note["explicit_non_authority"]


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


def test_preflight_exposes_bounded_seed_health_summary() -> None:
    report = build_federation_mutation_control_preflight()
    lifecycle_diag = report["bounded_federation_lifecycle_diagnostic"]
    seed_health = lifecycle_diag["bounded_federation_seed_health"]
    latest = lifecycle_diag["latest_lifecycle_by_intent"]

    assert len(latest) == 5
    assert set(seed_health["outcome_counts"]) == {
        "success",
        "denied",
        "failed_after_admission",
        "fragmented_unresolved",
    }
    assert isinstance(seed_health["has_fragmentation"], bool)
    assert isinstance(seed_health["has_admitted_failure"], bool)
    assert seed_health["support_signal_only"] is True
    temporal_view = lifecycle_diag["bounded_federation_seed_temporal_view"]
    assert temporal_view["history_path"].endswith("bounded_seed_health_history.jsonl")
    assert temporal_view["current_health_status"] in {"healthy", "degraded", "fragmented"}
    retrospective = temporal_view["retrospective_integrity_review"]
    assert retrospective["review_kind"] == "retrospective_integrity_review"
    assert retrospective["review_classification"] in {
        "clean_recent_history",
        "denial_heavy",
        "failure_heavy",
        "fragmentation_heavy",
        "oscillatory_instability",
        "mixed_stress_pattern",
        "insufficient_history",
    }
    assert retrospective["diagnostic_only"] is True
    assert retrospective["non_authoritative"] is True
    assert retrospective["decision_power"] == "none"
    assert retrospective["retrospective_support_signal_only"] is True
    assert retrospective["does_not_change_admission_or_readiness"] is True
    recommendation = temporal_view["operator_attention_recommendation"]
    assert recommendation["recommendation_kind"] == "operator_attention_recommendation"
    assert recommendation["recommended_attention"] in {
        "none",
        "observe",
        "inspect_recent_failures",
        "inspect_fragmentation",
        "watch_for_oscillation",
        "review_mixed_stress",
        "insufficient_context",
    }
    assert recommendation["diagnostic_only"] is True
    assert recommendation["recommendation_only"] is True
    assert recommendation["non_authoritative"] is True
    assert recommendation["decision_power"] == "none"
    assert recommendation["does_not_change_admission_or_readiness"] is True
    assert recommendation["does_not_change_authority_or_execution"] is True


def test_retrospective_review_does_not_change_readiness_or_authority_surfaces() -> None:
    baseline = build_federation_mutation_control_preflight()
    stressed = build_federation_mutation_control_preflight(
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

    assert baseline["readiness_verdict"] == "ready_for_initial_slice_onboarding"
    assert stressed["readiness_verdict"] == "ready_for_initial_slice_onboarding"
    retro = stressed["bounded_federation_lifecycle_diagnostic"]["bounded_federation_seed_temporal_view"]["retrospective_integrity_review"]
    recommendation = stressed["bounded_federation_lifecycle_diagnostic"]["bounded_federation_seed_temporal_view"][
        "operator_attention_recommendation"
    ]
    assert retro["does_not_change_admission_or_readiness"] is True
    assert retro["decision_power"] == "none"
    assert recommendation["does_not_change_admission_or_readiness"] is True
    assert recommendation["decision_power"] == "none"
