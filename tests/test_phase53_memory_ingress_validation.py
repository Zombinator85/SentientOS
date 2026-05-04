from __future__ import annotations

import pytest

from sentientos.embodiment_memory_ingress import (
    build_memory_ingress_validation_record,
    resolve_memory_ingress_validations,
    summarize_memory_ingress_validation_status,
    validate_memory_fulfillment_candidate,
)

pytestmark = pytest.mark.no_legacy_skip


def _candidate(kind: str = "memory_fulfillment_candidate", **overrides):
    row = {
        "fulfillment_candidate_id": "efc_1",
        "fulfillment_candidate_kind": kind,
        "source_governance_bridge_candidate_ref": "governance_bridge_candidate:gb1",
        "source_handoff_candidate_ref": "handoff_candidate:h1",
        "source_proposal_id": "p1",
        "source_review_receipt_id": "r1",
        "source_ingress_receipt_ref": "ing:p1",
        "source_event_refs": ["evt:p1"],
        "correlation_id": "c1",
        "source_module": "sentientos.embodiment_ingress",
        "privacy_retention_posture": "review",
        "consent_posture": "granted",
        "risk_flags": {},
        "candidate_payload_summary": {"summary": "ok"},
        "rationale": ["r"],
    }
    row.update(overrides)
    return row


def test_phase53_validation_builder_shape_and_non_authority_fields():
    row = build_memory_ingress_validation_record(memory_fulfillment_candidate=_candidate(), created_at=1.0)
    assert row["schema_version"].endswith("v1")
    assert row["decision_power"] == "none"
    assert row["non_authoritative"] is True
    assert row["validation_is_not_memory_write"] is True
    assert row["does_not_write_memory"] is True


def test_phase53_supported_kind_validates_for_future_write():
    row = validate_memory_fulfillment_candidate(memory_fulfillment_candidate=_candidate())
    assert row["validation_outcome"] == "memory_ingress_validated_for_future_write"


@pytest.mark.parametrize("kind", ["feedback_action_fulfillment_candidate", "screen_retention_fulfillment_candidate", "vision_retention_fulfillment_candidate", "multimodal_retention_fulfillment_candidate"])
def test_phase53_unsupported_kind_blocks(kind: str):
    row = validate_memory_fulfillment_candidate(memory_fulfillment_candidate=_candidate(kind=kind))
    assert row["validation_outcome"] == "memory_ingress_blocked_unsupported_kind"


def test_phase53_missing_consent_blocks_or_holds():
    row = validate_memory_fulfillment_candidate(memory_fulfillment_candidate=_candidate(consent_posture="not_asserted"))
    assert row["validation_outcome"] in {"memory_ingress_blocked_missing_consent", "memory_ingress_needs_more_context"}


def test_phase53_privacy_sensitive_blocks_without_allow_and_passes_with_allow():
    blocked = validate_memory_fulfillment_candidate(memory_fulfillment_candidate=_candidate(privacy_retention_posture="sensitive"))
    assert blocked["validation_outcome"] == "memory_ingress_blocked_privacy_sensitive"
    allowed = validate_memory_fulfillment_candidate(memory_fulfillment_candidate=_candidate(privacy_retention_posture="sensitive", risk_flags={"allow_privacy_sensitive_memory_ingress": True}))
    assert allowed["validation_outcome"] == "memory_ingress_validated_for_future_write"


def test_phase53_raw_retention_blocks_without_allow_and_passes_with_allow():
    blocked = validate_memory_fulfillment_candidate(memory_fulfillment_candidate=_candidate(risk_flags={"raw_retention_requested": True}))
    assert blocked["validation_outcome"] == "memory_ingress_blocked_raw_retention"
    allowed = validate_memory_fulfillment_candidate(memory_fulfillment_candidate=_candidate(risk_flags={"raw_retention_requested": True, "allow_raw_retention_memory_ingress": True}))
    assert allowed["validation_outcome"] == "memory_ingress_validated_for_future_write"


def test_phase53_missing_provenance_blocks():
    row = validate_memory_fulfillment_candidate(memory_fulfillment_candidate=_candidate(source_review_receipt_id=None))
    assert row["validation_outcome"] == "memory_ingress_blocked_missing_provenance"


def test_phase53_diagnostic_summary_counts_and_posture():
    rows = resolve_memory_ingress_validations(fulfillment_candidates=[
        _candidate(fulfillment_candidate_id="a"),
        _candidate(fulfillment_candidate_id="b", consent_posture="not_asserted"),
    ])["memory_ingress_validations"]
    summary = summarize_memory_ingress_validation_status(memory_ingress_validations=rows)
    assert summary["memory_ingress_validation_count"] == 2
    assert summary["memory_ingress_validated_for_future_write_count"] == 1
    assert summary["memory_ingress_blocked_count"] == 1
    assert summary["memory_ingress_posture"] == "mixed_memory_ingress_state"


def test_phase53_boundary_invariants():
    row = validate_memory_fulfillment_candidate(memory_fulfillment_candidate=_candidate())
    assert row["does_not_write_memory"] is True
    assert row["does_not_trigger_feedback"] is True
    assert row["does_not_admit_work"] is True
    assert row["does_not_execute_or_route_work"] is True
    assert row["decision_power"] == "none"
