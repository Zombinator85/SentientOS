from pathlib import Path

from sentientos.orchestration_spine.kernel.admission_handoff import (
    derive_packetization_gate_kernel,
    resolve_admission_handoff_outcome_kernel,
    resolve_handoff_packet_fulfillment_lifecycle_kernel,
    validate_handoff_minimum_fields_kernel,
)


def test_kernel_validate_handoff_minimum_fields_reports_missing_source_fields() -> None:
    missing = validate_handoff_minimum_fields_kernel(
        {
            "intent_id": "orh-1",
            "intent_kind": "internal_maintenance_execution",
            "execution_target": "task_admission_executor",
            "executability_classification": "executable_now",
            "source_delegated_judgment": {},
        }
    )
    assert "source_delegated_judgment.recommended_venue" in missing
    assert "source_delegated_judgment.work_class" in missing
    assert "source_delegated_judgment.escalation_classification" in missing


def test_kernel_resolve_admission_handoff_outcome_blocks_operator_requirement() -> None:
    intent = {
        "intent_id": "orh-1",
        "intent_kind": "operator_review_request",
        "execution_target": "no_execution_target_yet",
        "executability_classification": "blocked_operator_required",
        "required_authority_posture": "operator_approval_required",
        "requires_operator_approval": True,
        "source_delegated_judgment": {
            "recommended_venue": "operator_decision_required",
            "work_class": "operator_escalation",
            "escalation_classification": "operator_approval_required",
        },
    }

    outcome, details = resolve_admission_handoff_outcome_kernel(
        intent,
        validate_handoff_minimum_fields=validate_handoff_minimum_fields_kernel,
        handoff_outcomes={
            "staged_only",
            "admitted_to_execution_substrate",
            "blocked_by_admission",
            "blocked_by_operator_requirement",
            "blocked_by_insufficient_context",
            "execution_target_unavailable",
        },
        admit_internal_maintenance_intent=lambda **_kwargs: {"allowed": True},
        now_utc_iso=lambda: "2026-04-27T00:00:00Z",
        root=Path("."),
    )
    assert outcome == "blocked_by_operator_requirement"
    assert "task_admission" not in details


def test_kernel_packetization_gate_preserves_operator_decline_hold() -> None:
    gate = derive_packetization_gate_kernel(
        {
            "executability_classification": "executable_now",
            "relation_posture": "affirming",
            "proposed_next_action": {"proposed_posture": "expand"},
            "operator_escalation_requirement_state": {
                "requires_operator_or_escalation": False,
                "attention_signal": "none",
                "escalation_classification": "",
            },
        },
        {"review_classification": "coherent_recent_proposals"},
        {"trust_confidence_posture": "trusted_for_bounded_use", "pressure_summary": {"primary_pressure": "none"}},
        {"operator_attention_recommendation": "none"},
        anti_sovereignty_payload=lambda **_kwargs: {},
        packetization_gating_outcomes={
            "packetization_hold_operator_review",
            "packetization_hold_fragmentation",
            "packetization_hold_insufficient_confidence",
            "packetization_allowed_with_caution",
            "packetization_allowed",
            "packetization_hold_escalation_required",
        },
        operator_resolution_influence={
            "operator_decline_or_cancel_preserves_hold": True,
            "operator_influence_applied": True,
        },
    )
    assert gate["packetization_outcome"] == "packetization_hold_operator_review"
    assert gate["packetization_held"] is True


def test_kernel_handoff_packet_fulfillment_lifecycle_maps_receipts() -> None:
    lifecycle = resolve_handoff_packet_fulfillment_lifecycle_kernel(
        Path("."),
        {"handoff_packet_id": "pkt-1", "target_venue": "codex_implementation", "packet_status": "staged"},
        read_jsonl=lambda _path: [
            {
                "source_handoff_packet_ref": {"handoff_packet_id": "pkt-1"},
                "fulfillment_kind": "externally_abandoned",
                "fulfillment_receipt_id": "fr-1",
                "ingested_external_outcome": True,
            }
        ],
        staged_external_lifecycle_states={
            "staged_cleanly",
            "blocked_operator_required",
            "blocked_insufficient_context",
            "fulfilled_externally",
            "fulfilled_externally_with_issues",
            "externally_declined",
            "externally_abandoned",
            "externally_result_unusable",
            "fragmented_unlinked_work_order_state",
        },
    )
    assert lifecycle["lifecycle_state"] == "externally_abandoned"
    assert lifecycle["fulfillment_received"] is True
    assert lifecycle["fulfillment_receipt_id"] == "fr-1"
