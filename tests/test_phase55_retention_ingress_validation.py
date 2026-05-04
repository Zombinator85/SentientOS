from __future__ import annotations

from sentientos.embodiment_retention_ingress import (
    build_retention_ingress_validation_record,
    resolve_retention_ingress_validations,
    summarize_retention_ingress_validation_status,
    validate_retention_fulfillment_candidate,
)


def _candidate(**overrides):
    base = {
        "fulfillment_candidate_id": "rfc_1",
        "fulfillment_candidate_kind": "screen_retention_fulfillment_candidate",
        "source_governance_bridge_candidate_ref": "governance_bridge_candidate:g1",
        "source_handoff_candidate_ref": "handoff_candidate:h1",
        "source_proposal_id": "proposal_1",
        "source_review_receipt_id": "review_1",
        "source_ingress_receipt_ref": "embodiment_ingress_receipt:ir1",
        "source_event_refs": ["event:1"],
        "correlation_id": "corr-1",
        "source_module": "sentientos.embodiment_fulfillment",
        "consent_posture": "granted",
        "privacy_retention_posture": "low",
        "risk_flags": {},
        "candidate_payload_summary": {},
        "rationale": ["test"],
    }
    base.update(overrides)
    return base


def test_phase55_builder_shape_and_non_authority_fields():
    row = build_retention_ingress_validation_record(retention_fulfillment_candidate=_candidate(), created_at=1.0)
    assert row["schema_version"].endswith("v1")
    assert row["decision_power"] == "none"
    assert row["non_authoritative"] is True
    assert row["validation_is_not_retention_commit"] is True
    assert row["does_not_commit_retention"] is True


def test_phase55_supported_kinds_can_validate():
    screen = validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate())
    vision = validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate(fulfillment_candidate_id="rfc_2", fulfillment_candidate_kind="vision_retention_fulfillment_candidate"))
    multi = validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate(fulfillment_candidate_id="rfc_3", fulfillment_candidate_kind="multimodal_retention_fulfillment_candidate"))
    assert screen["validation_outcome"] == "retention_ingress_validated_for_future_commit"
    assert vision["validation_outcome"] == "retention_ingress_validated_for_future_commit"
    assert multi["validation_outcome"] == "retention_ingress_validated_for_future_commit"


def test_phase55_unsupported_kind_blocks():
    for kind in ("memory_fulfillment_candidate", "feedback_action_fulfillment_candidate"):
        row = validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate(fulfillment_candidate_kind=kind))
        assert row["validation_outcome"] == "retention_ingress_blocked_unsupported_kind"


def test_phase55_missing_consent_and_provenance_blocks():
    assert validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate(consent_posture="not_asserted"))["validation_outcome"] in {"retention_ingress_blocked_missing_consent", "retention_ingress_needs_more_context"}
    assert validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate(source_review_receipt_id=None))["validation_outcome"] == "retention_ingress_blocked_missing_provenance"


def test_phase55_privacy_and_raw_retention_rules():
    assert validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate(privacy_retention_posture="sensitive"))["validation_outcome"] == "retention_ingress_blocked_privacy_sensitive"
    assert validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate(privacy_retention_posture="sensitive", risk_flags={"allow_privacy_sensitive_retention_ingress": True}))["validation_outcome"] == "retention_ingress_validated_for_future_commit"
    assert validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate(risk_flags={"raw_retention_requested": True}))["validation_outcome"] == "retention_ingress_blocked_raw_retention"
    assert validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate(risk_flags={"raw_retention_requested": True, "allow_raw_retention_ingress": True}))["validation_outcome"] == "retention_ingress_validated_for_future_commit"


def test_phase55_vision_biometric_and_multimodal_context_rules():
    v_block = validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate(fulfillment_candidate_kind="vision_retention_fulfillment_candidate", risk_flags={"biometric_sensitive": True}))
    assert v_block["validation_outcome"] == "retention_ingress_blocked_biometric_or_emotion_sensitive"
    v_ok = validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate(fulfillment_candidate_kind="vision_retention_fulfillment_candidate", risk_flags={"biometric_sensitive": True, "allow_biometric_or_emotion_sensitive_retention_ingress": True}))
    assert v_ok["validation_outcome"] == "retention_ingress_validated_for_future_commit"

    m_block = validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate(fulfillment_candidate_kind="multimodal_retention_fulfillment_candidate", risk_flags={"multimodal_context_sensitive": True}))
    assert m_block["validation_outcome"] == "retention_ingress_blocked_multimodal_context_sensitive"
    m_ok = validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate(fulfillment_candidate_kind="multimodal_retention_fulfillment_candidate", risk_flags={"multimodal_context_sensitive": True, "allow_multimodal_context_sensitive_retention_ingress": True}))
    assert m_ok["validation_outcome"] == "retention_ingress_validated_for_future_commit"


def test_phase55_operator_confirmation_hold_unless_confirmed():
    hold = validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate(candidate_payload_summary={"requires_operator_confirmation": True}))
    assert hold["validation_outcome"] == "retention_ingress_needs_more_context"
    ok = validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate(candidate_payload_summary={"requires_operator_confirmation": True, "operator_confirmation_present": True}))
    assert ok["validation_outcome"] == "retention_ingress_validated_for_future_commit"


def test_phase55_diagnostic_summary_counts_kind_and_posture():
    rows = resolve_retention_ingress_validations(fulfillment_candidates=[
        _candidate(fulfillment_candidate_id="a", fulfillment_candidate_kind="screen_retention_fulfillment_candidate"),
        _candidate(fulfillment_candidate_id="b", fulfillment_candidate_kind="vision_retention_fulfillment_candidate", risk_flags={"biometric_sensitive": True}),
    ])["retention_ingress_validations"]
    summary = summarize_retention_ingress_validation_status(retention_ingress_validations=rows)
    assert summary["retention_ingress_validation_count"] == 2
    assert summary["retention_ingress_validated_for_future_commit_count"] == 1
    assert summary["retention_ingress_blocked_count"] == 1
    assert summary["retention_ingress_counts_by_candidate_kind"]["screen_retention_fulfillment_candidate"] == 1
    assert summary["retention_ingress_posture"] == "mixed_retention_ingress_state"


def test_phase55_boundary_invariants():
    row = validate_retention_fulfillment_candidate(retention_fulfillment_candidate=_candidate())
    assert row["does_not_commit_retention"] is True
    assert row["does_not_write_memory"] is True
    assert row["does_not_trigger_feedback"] is True
    assert row["does_not_admit_work"] is True
    assert row["does_not_execute_or_route_work"] is True
    assert row["decision_power"] == "none"
