from __future__ import annotations

import pytest

from sentientos.embodiment_action_ingress import (
    build_action_ingress_validation_record,
    resolve_action_ingress_validations,
    summarize_action_ingress_validation_status,
    validate_action_fulfillment_candidate,
)

pytestmark = pytest.mark.no_legacy_skip


def _candidate(kind: str = "feedback_action_fulfillment_candidate", **overrides):
    row = {
        "fulfillment_candidate_id": "efc_a1",
        "fulfillment_candidate_kind": kind,
        "source_governance_bridge_candidate_ref": "governance_bridge_candidate:gb1",
        "source_handoff_candidate_ref": "handoff_candidate:h1",
        "source_proposal_id": "p1",
        "source_review_receipt_id": "r1",
        "source_ingress_receipt_ref": "ingress_receipt:ir1",
        "source_event_refs": ["evt:1"],
        "correlation_id": "corr-1",
        "source_module": "sentientos.embodiment_fulfillment",
        "privacy_retention_posture": "review",
        "consent_posture": "granted",
        "risk_flags": {},
        "candidate_payload_summary": {"action": "notify_operator"},
        "rationale": ["ok"],
    }
    row.update(overrides)
    return row


def test_phase54_validation_builder_shape_and_non_authority_fields():
    row = build_action_ingress_validation_record(feedback_action_fulfillment_candidate=_candidate(), created_at=1.0)
    assert row["schema_version"].endswith("v1")
    assert row["decision_power"] == "none"
    assert row["non_authoritative"] is True
    assert row["validation_is_not_action_trigger"] is True
    assert row["does_not_trigger_feedback"] is True


def test_phase54_supported_kind_validates_for_future_trigger():
    row = validate_action_fulfillment_candidate(feedback_action_fulfillment_candidate=_candidate())
    assert row["validation_outcome"] == "action_ingress_validated_for_future_trigger"


@pytest.mark.parametrize("kind", ["memory_fulfillment_candidate", "screen_retention_fulfillment_candidate", "vision_retention_fulfillment_candidate", "multimodal_retention_fulfillment_candidate"])
def test_phase54_unsupported_kind_blocks(kind: str):
    row = validate_action_fulfillment_candidate(feedback_action_fulfillment_candidate=_candidate(kind=kind))
    assert row["validation_outcome"] == "action_ingress_blocked_unsupported_kind"


def test_phase54_missing_consent_blocks_or_holds():
    row = validate_action_fulfillment_candidate(feedback_action_fulfillment_candidate=_candidate(consent_posture="not_asserted"))
    assert row["validation_outcome"] in {"action_ingress_blocked_missing_consent", "action_ingress_needs_more_context"}


def test_phase54_missing_provenance_blocks():
    row = validate_action_fulfillment_candidate(feedback_action_fulfillment_candidate=_candidate(source_review_receipt_id=None))
    assert row["validation_outcome"] == "action_ingress_blocked_missing_provenance"


def test_phase54_privacy_sensitive_blocks_unless_allowed():
    blocked = validate_action_fulfillment_candidate(feedback_action_fulfillment_candidate=_candidate(privacy_retention_posture="sensitive"))
    assert blocked["validation_outcome"] == "action_ingress_blocked_privacy_sensitive"
    allowed = validate_action_fulfillment_candidate(feedback_action_fulfillment_candidate=_candidate(privacy_retention_posture="sensitive", risk_flags={"allow_privacy_sensitive_action_ingress": True}))
    assert allowed["validation_outcome"] == "action_ingress_validated_for_future_trigger"


def test_phase54_unsafe_and_high_risk_block_unless_allowed():
    unsafe = validate_action_fulfillment_candidate(feedback_action_fulfillment_candidate=_candidate(risk_flags={"unsafe_action": True}))
    assert unsafe["validation_outcome"] == "action_ingress_blocked_unsafe_action"
    unsafe_ok = validate_action_fulfillment_candidate(feedback_action_fulfillment_candidate=_candidate(risk_flags={"unsafe_action": True, "allow_unsafe_action_ingress": True}))
    assert unsafe_ok["validation_outcome"] == "action_ingress_validated_for_future_trigger"

    high = validate_action_fulfillment_candidate(feedback_action_fulfillment_candidate=_candidate(risk_flags={"high_risk_action": True}))
    assert high["validation_outcome"] == "action_ingress_blocked_high_risk_action"
    high_ok = validate_action_fulfillment_candidate(feedback_action_fulfillment_candidate=_candidate(risk_flags={"high_risk_action": True, "allow_high_risk_action_ingress": True}))
    assert high_ok["validation_outcome"] == "action_ingress_validated_for_future_trigger"


def test_phase54_operator_confirmation_requires_context_unless_confirmed():
    hold = validate_action_fulfillment_candidate(feedback_action_fulfillment_candidate=_candidate(candidate_payload_summary={"requires_operator_confirmation": True}))
    assert hold["validation_outcome"] == "action_ingress_needs_more_context"
    ok = validate_action_fulfillment_candidate(feedback_action_fulfillment_candidate=_candidate(candidate_payload_summary={"requires_operator_confirmation": True, "operator_confirmation_present": True}))
    assert ok["validation_outcome"] == "action_ingress_validated_for_future_trigger"


def test_phase54_diagnostic_summary_counts_and_posture():
    rows = resolve_action_ingress_validations(fulfillment_candidates=[
        _candidate(fulfillment_candidate_id="a"),
        _candidate(fulfillment_candidate_id="b", consent_posture="not_asserted"),
    ])["action_ingress_validations"]
    summary = summarize_action_ingress_validation_status(action_ingress_validations=rows)
    assert summary["action_ingress_validation_count"] == 2
    assert summary["action_ingress_validated_for_future_trigger_count"] == 1
    assert summary["action_ingress_blocked_count"] == 1
    assert summary["action_ingress_posture"] == "mixed_action_ingress_state"


def test_phase54_boundary_invariants():
    row = validate_action_fulfillment_candidate(feedback_action_fulfillment_candidate=_candidate())
    assert row["does_not_trigger_feedback"] is True
    assert row["does_not_execute_or_route_work"] is True
    assert row["does_not_admit_work"] is True
    assert row["does_not_write_memory"] is True
    assert row["decision_power"] == "none"
