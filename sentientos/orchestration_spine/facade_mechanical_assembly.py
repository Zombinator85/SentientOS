from __future__ import annotations

"""Mechanical-only façade assembly helpers extracted from orchestration_intent_fabric.

These helpers are intentionally narrow and non-authoritative:
- no schema-envelope shaping
- no authority decisions
- no ledger append behavior
"""

from typing import Any, Mapping


def handoff_evidence_pointers(delegated_judgment: Mapping[str, Any]) -> list[str]:
    """Build compact, deduplicated artifact pointers while preserving insertion order."""

    delegated_basis = delegated_judgment.get("basis")
    delegated_basis_map = delegated_basis if isinstance(delegated_basis, Mapping) else {}
    pointers = [
        "glow/orchestration/orchestration_next_move_proposals.jsonl",
        "glow/orchestration/orchestration_handoffs.jsonl",
        "glow/orchestration/orchestration_intents.jsonl",
    ]
    artifacts = delegated_basis_map.get("artifacts_read")
    if isinstance(artifacts, Mapping):
        for value in artifacts.values():
            if isinstance(value, str) and value:
                pointers.append(value)

    seen: set[str] = set()
    ordered: list[str] = []
    for pointer in pointers:
        if pointer not in seen:
            ordered.append(pointer)
            seen.add(pointer)
    return ordered


def normalized_compact_string_refs(values: list[str] | None) -> list[str]:
    """Normalize optional free-form refs into compact, non-empty string rows."""

    return [
        value.strip()
        for value in (values or [])
        if isinstance(value, str) and value.strip()
    ]


def staged_work_order_id(
    intent: Mapping[str, Any],
    created_at: str,
    *,
    prefix: str,
    stable_prefixed_id: Any,
) -> str:
    """Build deterministic staged-work-order ids via injected stable id primitive."""

    return stable_prefixed_id(
        f"{prefix}-wo",
        {
            "created_at": created_at,
            "intent_id": str(intent.get("intent_id") or ""),
            "source_judgment": dict(intent.get("source_delegated_judgment") or {}),
        },
    )


def fulfillment_receipt_id(
    *,
    created_at: str,
    handoff_packet_id: str,
    venue: str,
    fulfillment_kind: str,
    stable_prefixed_id: Any,
) -> str:
    """Build deterministic fulfillment receipt ids via injected stable id primitive."""

    return stable_prefixed_id(
        "frc",
        {
            "created_at": created_at,
            "handoff_packet_id": handoff_packet_id,
            "venue": venue,
            "fulfillment_kind": fulfillment_kind,
        },
    )


def operator_resolution_receipt_id(
    *,
    created_at: str,
    operator_action_brief_id: str,
    resolution_kind: str,
    stable_prefixed_id: Any,
) -> str:
    """Build deterministic operator-resolution receipt ids via injected id primitive."""

    return stable_prefixed_id(
        "orr",
        {
            "created_at": created_at,
            "operator_action_brief_id": operator_action_brief_id,
            "resolution_kind": resolution_kind,
        },
    )


def staged_external_work_order_status(
    handoff_outcome: str,
    *,
    staged_external_work_order_statuses: set[str],
) -> str:
    """Resolve staged external work-order status from handoff outcome."""

    if handoff_outcome == "blocked_by_operator_requirement":
        status = "blocked_operator_required"
    elif handoff_outcome == "blocked_by_insufficient_context":
        status = "blocked_insufficient_context"
    else:
        status = "staged"

    if status not in staged_external_work_order_statuses:
        return "blocked_insufficient_context"
    return status


def staged_external_work_order_lifecycle_state(
    *,
    handoff_outcome: str,
    latest_work_order_status: str,
    work_order_present: bool,
    staged_external_lifecycle_states: set[str],
) -> str:
    """Resolve lifecycle-state classification from latest linked work-order status."""

    if not work_order_present:
        lifecycle_state = "fragmented_unlinked_work_order_state"
    elif handoff_outcome == "blocked_by_operator_requirement":
        lifecycle_state = "blocked_operator_required"
    elif handoff_outcome == "blocked_by_insufficient_context":
        lifecycle_state = "blocked_insufficient_context"
    elif latest_work_order_status == "staged":
        lifecycle_state = "staged_cleanly"
    elif latest_work_order_status == "fulfilled_externally_unverified":
        lifecycle_state = "fulfilled_externally_with_issues"
    else:
        lifecycle_state = "fragmented_unlinked_work_order_state"

    if lifecycle_state not in staged_external_lifecycle_states:
        return "fragmented_unlinked_work_order_state"
    return lifecycle_state


def operator_resolution_lifecycle_state(resolution_kind: str) -> str:
    """Map operator resolution kind to stable receipt lifecycle-state label."""

    return {
        "approved_continue": "operator_approved_continue",
        "approved_with_constraints": "operator_approved_with_constraints",
        "declined": "operator_declined",
        "deferred": "operator_deferred",
        "supplied_missing_context": "operator_supplied_missing_context",
        "redirected_venue": "operator_redirected",
        "cancelled": "operator_declined",
    }[resolution_kind]
