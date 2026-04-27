from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping


def _unified_result_id(
    *,
    intent_id: str,
    handoff_outcome: str,
    handoff_packet_id: str,
    venue: str,
    resolution_path: str,
) -> str:
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            {
                "intent_id": intent_id,
                "handoff_outcome": handoff_outcome,
                "handoff_packet_id": handoff_packet_id,
                "venue": venue,
                "resolution_path": resolution_path,
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    return f"oru-{digest.hexdigest()[:16]}"


def _classify_internal_resolution(
    handoff: Mapping[str, Any],
    internal_resolution: Mapping[str, Any],
) -> str:
    state = str(internal_resolution.get("orchestration_result_state") or "execution_result_missing")
    handoff_outcome = str(handoff.get("handoff_outcome") or "")
    if state == "execution_succeeded":
        return "completed_successfully"
    if state == "execution_failed":
        return "failed_after_execution"
    if state in {"handoff_admitted_pending_result", "execution_still_pending"}:
        return "pending_or_unresolved"
    if state == "execution_result_missing":
        return "fragmented_result_history"
    if handoff_outcome in {
        "blocked_by_admission",
        "blocked_by_operator_requirement",
        "blocked_by_insufficient_context",
        "execution_target_unavailable",
    }:
        return "blocked_before_execution"
    return "pending_or_unresolved"


def _classify_external_lifecycle(lifecycle_state: str) -> str:
    return {
        "fulfilled_externally": "completed_successfully",
        "fulfilled_externally_with_issues": "completed_with_issues",
        "externally_declined": "declined_or_abandoned",
        "externally_abandoned": "declined_or_abandoned",
        "externally_result_unusable": "failed_after_execution",
        "blocked_operator_required": "blocked_before_execution",
        "blocked_insufficient_context": "blocked_before_execution",
        "staged_cleanly": "pending_or_unresolved",
        "fragmented_unlinked_work_order_state": "fragmented_result_history",
    }.get(lifecycle_state, "fragmented_result_history")


def resolve_unified_orchestration_result_kernel(
    repo_root: Path,
    *,
    handoff: Mapping[str, Any] | None,
    handoff_packet: Mapping[str, Any] | None,
    executor_log_path: Path | None,
    resolve_orchestration_result: Callable[..., Mapping[str, Any]],
    resolve_handoff_packet_fulfillment_lifecycle: Callable[..., Mapping[str, Any]],
    iso_utc_now: Callable[[], str],
    unified_result_classifications: set[str],
    unified_result_resolution_paths: set[str],
) -> dict[str, Any]:
    """Resolve one bounded venue-aware orchestration result over internal/external closure paths."""

    root = repo_root.resolve()
    handoff_map = handoff if isinstance(handoff, Mapping) else {}
    packet_map = handoff_packet if isinstance(handoff_packet, Mapping) else {}
    intent_ref = handoff_map.get("intent_ref")
    intent_ref_map = intent_ref if isinstance(intent_ref, Mapping) else {}
    intent_id = str(intent_ref_map.get("intent_id") or "")
    intent_kind = str(intent_ref_map.get("intent_kind") or "")
    handoff_outcome = str(handoff_map.get("handoff_outcome") or "")
    target_venue = str(packet_map.get("target_venue") or "")
    packet_id = str(packet_map.get("handoff_packet_id") or "")

    is_external = target_venue in {"codex_implementation", "deep_research_audit"} or intent_kind in {
        "codex_work_order",
        "deep_research_work_order",
    }
    resolution_path = "external_fulfillment" if is_external else "internal_execution"
    if resolution_path not in unified_result_resolution_paths:
        resolution_path = "internal_execution"

    classification = "fragmented_result_history"
    task_result_observed = False
    fulfillment_receipt_observed = False
    result_state = "fragmented_unlinked_work_order_state" if is_external else "execution_result_missing"
    internal_resolution: dict[str, Any] | None = None
    external_lifecycle: dict[str, Any] | None = None
    fragmented_linkage = False

    if resolution_path == "internal_execution":
        if not handoff_map:
            fragmented_linkage = True
        else:
            internal_resolution = dict(resolve_orchestration_result(root, handoff_map, executor_log_path=executor_log_path))
            result_state = str(internal_resolution.get("orchestration_result_state") or "execution_result_missing")
            task_result_observed = bool(internal_resolution.get("execution_observed"))
            classification = _classify_internal_resolution(handoff_map, internal_resolution)
            if not intent_id:
                fragmented_linkage = True
    else:
        if not packet_map:
            fragmented_linkage = True
        else:
            external_lifecycle = dict(resolve_handoff_packet_fulfillment_lifecycle(root, packet_map))
            lifecycle_state = str(external_lifecycle.get("lifecycle_state") or "fragmented_unlinked_work_order_state")
            result_state = lifecycle_state
            fulfillment_receipt_observed = bool(external_lifecycle.get("fulfillment_received"))
            classification = _classify_external_lifecycle(lifecycle_state)
            if not packet_id:
                fragmented_linkage = True
            if not handoff_map:
                fragmented_linkage = True

    if fragmented_linkage:
        classification = "fragmented_result_history"
    if classification not in unified_result_classifications:
        classification = "fragmented_result_history"

    operator_state = (
        packet_map.get("operator_escalation_requirement_state")
        if isinstance(packet_map.get("operator_escalation_requirement_state"), Mapping)
        else handoff_map.get("details", {})
        if isinstance(handoff_map.get("details"), Mapping)
        else {}
    )
    operator_state_map = operator_state if isinstance(operator_state, Mapping) else {}
    venue = target_venue or ("task_admission_executor" if resolution_path == "internal_execution" else "insufficient_context")

    result: dict[str, Any] = {
        "schema_version": "orchestration_unified_result.v1",
        "resolved_at": iso_utc_now(),
        "orchestration_result_id": _unified_result_id(
            intent_id=intent_id,
            handoff_outcome=handoff_outcome,
            handoff_packet_id=packet_id,
            venue=venue,
            resolution_path=resolution_path,
        ),
        "source_intent_ref": {
            "intent_id": intent_id or None,
            "intent_kind": intent_kind or None,
            "intent_ledger_path": "glow/orchestration/orchestration_intents.jsonl",
        },
        "source_linkage": {
            "handoff_outcome": handoff_outcome or None,
            "handoff_ledger_path": "glow/orchestration/orchestration_handoffs.jsonl" if handoff_map else None,
            "handoff_packet_id": packet_id or None,
            "handoff_packet_ledger_path": "glow/orchestration/orchestration_handoff_packets.jsonl" if packet_map else None,
        },
        "venue": venue,
        "resolution_path": resolution_path,
        "result_classification": classification,
        "resolution_state": result_state,
        "evidence_presence": {
            "task_result_observed": task_result_observed,
            "fulfillment_receipt_observed": fulfillment_receipt_observed,
            "proof_linkage_present": not fragmented_linkage,
            "fragmented_linkage": fragmented_linkage,
        },
        "operator_escalation_context": {
            "requires_operator_or_escalation": bool(operator_state_map.get("requires_operator_or_escalation")),
            "requires_operator_approval": bool(operator_state_map.get("requires_operator_approval")),
            "escalation_classification": str(operator_state_map.get("escalation_classification") or ""),
        },
        "path_honesty": {
            "ingested_external_outcome": bool((external_lifecycle or {}).get("ingested_external_outcome")),
            "does_not_imply_direct_repo_execution": resolution_path == "external_fulfillment",
            "task_result_observed": task_result_observed,
            "fulfillment_receipt_observed": fulfillment_receipt_observed,
        },
        "non_authoritative": True,
        "decision_power": "none",
    }
    if internal_resolution is not None:
        result["internal_resolution"] = internal_resolution
    if external_lifecycle is not None:
        result["external_fulfillment_lifecycle"] = external_lifecycle
    return result
