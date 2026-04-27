from pathlib import Path

from sentientos.orchestration_spine.kernel.unified_results import resolve_unified_orchestration_result_kernel


def test_kernel_unified_result_internal_execution_path() -> None:
    handoff = {
        "intent_ref": {"intent_id": "intent-1", "intent_kind": "internal_maintenance_execution"},
        "handoff_outcome": "admitted_to_execution_substrate",
        "details": {"requires_operator_or_escalation": False},
    }

    result = resolve_unified_orchestration_result_kernel(
        Path("."),
        handoff=handoff,
        handoff_packet={},
        executor_log_path=None,
        resolve_orchestration_result=lambda *_args, **_kwargs: {
            "orchestration_result_state": "execution_succeeded",
            "execution_observed": True,
        },
        resolve_handoff_packet_fulfillment_lifecycle=lambda *_args, **_kwargs: {},
        iso_utc_now=lambda: "2026-04-27T00:00:00+00:00",
        unified_result_classifications={
            "completed_successfully",
            "completed_with_issues",
            "declined_or_abandoned",
            "failed_after_execution",
            "blocked_before_execution",
            "pending_or_unresolved",
            "fragmented_result_history",
        },
        unified_result_resolution_paths={"internal_execution", "external_fulfillment"},
    )

    assert result["resolution_path"] == "internal_execution"
    assert result["result_classification"] == "completed_successfully"
    assert result["evidence_presence"]["task_result_observed"] is True
    assert result["evidence_presence"]["proof_linkage_present"] is True
    assert result["path_honesty"]["does_not_imply_direct_repo_execution"] is False


def test_kernel_unified_result_external_path_marks_fragmented_when_handoff_missing() -> None:
    packet = {
        "handoff_packet_id": "pkt-1",
        "target_venue": "codex_implementation",
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": True,
            "requires_operator_approval": True,
            "escalation_classification": "operator_approval_required",
        },
    }

    result = resolve_unified_orchestration_result_kernel(
        Path("."),
        handoff=None,
        handoff_packet=packet,
        executor_log_path=None,
        resolve_orchestration_result=lambda *_args, **_kwargs: {},
        resolve_handoff_packet_fulfillment_lifecycle=lambda *_args, **_kwargs: {
            "lifecycle_state": "fulfilled_externally",
            "fulfillment_received": True,
            "ingested_external_outcome": True,
        },
        iso_utc_now=lambda: "2026-04-27T00:00:00+00:00",
        unified_result_classifications={
            "completed_successfully",
            "completed_with_issues",
            "declined_or_abandoned",
            "failed_after_execution",
            "blocked_before_execution",
            "pending_or_unresolved",
            "fragmented_result_history",
        },
        unified_result_resolution_paths={"internal_execution", "external_fulfillment"},
    )

    assert result["resolution_path"] == "external_fulfillment"
    assert result["evidence_presence"]["fragmented_linkage"] is True
    assert result["result_classification"] == "fragmented_result_history"
    assert result["path_honesty"]["fulfillment_receipt_observed"] is True
