from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import task_admission
import task_executor

_INTENT_KINDS = {
    "internal_maintenance_execution",
    "codex_work_order",
    "deep_research_work_order",
    "operator_review_request",
    "hold_no_action",
}

_AUTHORITY_POSTURES = {
    "no_additional_operator_approval_required",
    "operator_approval_required",
    "operator_priority_required",
    "insufficient_context_blocked",
}

_EXECUTION_TARGETS = {
    "task_admission_executor",
    "mutation_router",
    "federation_canonical_execution",
    "no_execution_target_yet",
    "external_tool_placeholder",
}

_EXECUTABILITY = {
    "executable_now",
    "stageable_external_work_order",
    "blocked_operator_required",
    "blocked_insufficient_context",
    "no_action_recommended",
}

_ADMISSION_STATES = {
    "admitted_for_internal_staging",
    "deferred_operator_approval",
    "deferred_operator_priority",
    "deferred_insufficient_context",
    "staged_non_executable_work_order",
    "no_action",
}

_HANDOFF_OUTCOMES = {
    "staged_only",
    "admitted_to_execution_substrate",
    "blocked_by_admission",
    "blocked_by_operator_requirement",
    "blocked_by_insufficient_context",
    "execution_target_unavailable",
}

_EXECUTION_RESULT_STATES = {
    "handoff_admitted_pending_result",
    "execution_succeeded",
    "execution_failed",
    "execution_result_missing",
    "execution_still_pending",
    "handoff_not_admitted",
}


_STAGED_EXTERNAL_WORK_ORDER_STATUSES = {
    "staged",
    "blocked_operator_required",
    "blocked_insufficient_context",
    "cancelled",
    "fulfilled_externally_unverified",
}

_STAGED_EXTERNAL_LIFECYCLE_STATES = {
    "staged_cleanly",
    "blocked_operator_required",
    "blocked_insufficient_context",
    "fragmented_unlinked_work_order_state",
}

_ORCHESTRATION_REVIEW_CLASSES = {
    "clean_recent_orchestration",
    "handoff_block_heavy",
    "execution_failure_heavy",
    "pending_stall_pattern",
    "mixed_orchestration_stress",
    "insufficient_history",
}

_ORCHESTRATION_ATTENTION_RECOMMENDATIONS = {
    "none",
    "observe",
    "inspect_handoff_blocks",
    "inspect_execution_failures",
    "inspect_pending_stall",
    "review_mixed_orchestration_stress",
    "insufficient_context",
}


def _anti_sovereignty_payload(
    *,
    recommendation_only: bool,
    diagnostic_only: bool,
    does_not_invoke_external_tools: bool | None = None,
    does_not_change_admission_or_execution: bool | None = None,
    additional_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "non_authoritative": True,
        "decision_power": "none",
        "recommendation_only": recommendation_only,
        "diagnostic_only": diagnostic_only,
    }
    if does_not_invoke_external_tools is not None:
        payload["does_not_invoke_external_tools"] = does_not_invoke_external_tools
    if does_not_change_admission_or_execution is not None:
        payload["does_not_change_admission_or_execution"] = does_not_change_admission_or_execution
    if additional_fields:
        payload.update(dict(additional_fields))
    return payload


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _intent_id(source_judgment: Mapping[str, Any], created_at: str) -> str:
    canonical = json.dumps({"created_at": created_at, "source_judgment": source_judgment}, sort_keys=True, separators=(",", ":"))
    return f"orh-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _classify_authority_posture(judgment: Mapping[str, Any]) -> str:
    escalation = str(judgment.get("escalation_classification") or "")
    venue = str(judgment.get("recommended_venue") or "")
    if escalation == "escalate_for_missing_context" or venue == "insufficient_context":
        return "insufficient_context_blocked"
    if escalation == "escalate_for_operator_priority":
        return "operator_priority_required"
    if venue in {"codex_implementation", "deep_research_audit", "operator_decision_required"}:
        return "operator_approval_required"
    return "no_additional_operator_approval_required"


def _translate_kind(judgment: Mapping[str, Any]) -> tuple[str, str, str]:
    venue = str(judgment.get("recommended_venue") or "")
    work_class = str(judgment.get("work_class") or "")
    escalation = str(judgment.get("escalation_classification") or "")

    if escalation == "escalate_for_missing_context" or venue == "insufficient_context":
        return "hold_no_action", "no_execution_target_yet", "blocked_insufficient_context"

    if venue == "internal_direct_execution" and work_class == "internal_runtime_maintenance":
        return "internal_maintenance_execution", "task_admission_executor", "executable_now"

    if venue == "codex_implementation":
        return "codex_work_order", "no_execution_target_yet", "stageable_external_work_order"

    if venue == "deep_research_audit":
        return "deep_research_work_order", "no_execution_target_yet", "stageable_external_work_order"

    if venue == "operator_decision_required":
        return "operator_review_request", "no_execution_target_yet", "blocked_operator_required"

    if work_class == "external_tool_orchestration":
        return "operator_review_request", "external_tool_placeholder", "stageable_external_work_order"

    return "hold_no_action", "no_execution_target_yet", "no_action_recommended"


def _derive_admission_state(executability: str, authority_posture: str) -> str:
    if executability == "executable_now" and authority_posture == "no_additional_operator_approval_required":
        return "admitted_for_internal_staging"
    if authority_posture == "operator_priority_required":
        return "deferred_operator_priority"
    if authority_posture == "insufficient_context_blocked":
        return "deferred_insufficient_context"
    if executability == "stageable_external_work_order":
        return "staged_non_executable_work_order"
    if executability == "blocked_operator_required":
        return "deferred_operator_approval"
    return "no_action"


def _source_judgment_linkage(judgment: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "work_class": str(judgment.get("work_class") or "operator_required"),
        "recommended_venue": str(judgment.get("recommended_venue") or "insufficient_context"),
        "next_move_posture": str(judgment.get("next_move_posture") or "hold"),
        "consolidation_expansion_posture": str(judgment.get("consolidation_expansion_posture") or "insufficient_context"),
        "escalation_classification": str(judgment.get("escalation_classification") or "escalate_for_missing_context"),
        "readiness_basis": {
            "orchestration_substitution_readiness": judgment.get("orchestration_substitution_readiness", {}),
            "basis": judgment.get("basis", {}),
        },
    }


def _work_order_payload(intent_kind: str, source_linkage: Mapping[str, Any], executability: str, authority_posture: str) -> dict[str, Any] | None:
    if intent_kind not in {"codex_work_order", "deep_research_work_order", "operator_review_request"}:
        return None

    venue = str(source_linkage.get("recommended_venue") or "")
    rationale = source_linkage.get("readiness_basis", {}).get("basis", {}) if isinstance(source_linkage.get("readiness_basis"), Mapping) else {}
    return {
        "work_order_kind": intent_kind,
        "intended_venue": venue,
        "bounded_rationale": {
            "signal_reasons": list(rationale.get("signal_reasons") or []),
            "slice_health_status": rationale.get("slice_health_status"),
            "slice_stability_classification": rationale.get("slice_stability_classification"),
            "slice_review_classification": rationale.get("slice_review_classification"),
        },
        "authority_posture": authority_posture,
        "executability_classification": executability,
        "staged_only": executability != "executable_now",
    }


def synthesize_orchestration_intent(
    delegated_judgment: Mapping[str, Any],
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Translate delegated judgment into a bounded, governed orchestration intent."""

    source_linkage = _source_judgment_linkage(delegated_judgment)
    authority_posture = _classify_authority_posture(delegated_judgment)
    intent_kind, execution_target, executability = _translate_kind(delegated_judgment)
    admission_state = _derive_admission_state(executability, authority_posture)
    timestamp = created_at or _iso_utc_now()
    intent_id = _intent_id(source_linkage, timestamp)

    if intent_kind not in _INTENT_KINDS:
        intent_kind = "hold_no_action"
    if authority_posture not in _AUTHORITY_POSTURES:
        authority_posture = "insufficient_context_blocked"
    if execution_target not in _EXECUTION_TARGETS:
        execution_target = "no_execution_target_yet"
    if executability not in _EXECUTABILITY:
        executability = "blocked_insufficient_context"
    if admission_state not in _ADMISSION_STATES:
        admission_state = "deferred_insufficient_context"

    requires_operator_approval = authority_posture != "no_additional_operator_approval_required"
    work_order = _work_order_payload(intent_kind, source_linkage, executability, authority_posture)

    return {
        "schema_version": "orchestration_intent.v1",
        "intent_id": intent_id,
        "created_at": timestamp,
        "intent_kind": intent_kind,
        "source_delegated_judgment": source_linkage,
        "required_authority_posture": authority_posture,
        "execution_target": execution_target,
        "executability_classification": executability,
        "handoff_admission_state": admission_state,
        "work_order": work_order,
        "requires_admission": execution_target in {"task_admission_executor", "mutation_router", "federation_canonical_execution"},
        "requires_operator_approval": requires_operator_approval,
        **_anti_sovereignty_payload(
            recommendation_only=False,
            diagnostic_only=False,
            does_not_invoke_external_tools=True,
        ),
        "staged_handoff_only": executability != "executable_now",
        "does_not_override_existing_admission": True,
        "does_not_override_kernel_or_governor": True,
        "does_not_replace_operator_authority": True,
    }


def append_orchestration_intent_ledger(repo_root: Path, intent: Mapping[str, Any]) -> Path:
    """Append one orchestration intent to the proof-visible handoff ledger."""

    ledger_path = repo_root.resolve() / "glow/orchestration/orchestration_intents.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(intent), sort_keys=True) + "\n")
    return ledger_path


def _validate_handoff_minimum_fields(intent: Mapping[str, Any]) -> list[str]:
    missing: list[str] = []
    if not str(intent.get("intent_id") or "").strip():
        missing.append("intent_id")
    if not str(intent.get("intent_kind") or "").strip():
        missing.append("intent_kind")
    if not str(intent.get("execution_target") or "").strip():
        missing.append("execution_target")
    if not str(intent.get("executability_classification") or "").strip():
        missing.append("executability_classification")
    source = intent.get("source_delegated_judgment")
    if not isinstance(source, Mapping):
        missing.append("source_delegated_judgment")
        return missing
    if not str(source.get("recommended_venue") or "").strip():
        missing.append("source_delegated_judgment.recommended_venue")
    if not str(source.get("work_class") or "").strip():
        missing.append("source_delegated_judgment.work_class")
    if not str(source.get("escalation_classification") or "").strip():
        missing.append("source_delegated_judgment.escalation_classification")
    return missing


def _build_internal_maintenance_task(intent: Mapping[str, Any]) -> task_executor.Task:
    source = intent.get("source_delegated_judgment")
    source_mapping = source if isinstance(source, Mapping) else {}
    return task_executor.Task(
        task_id=f"orh-{str(intent.get('intent_id') or 'missing')}",
        objective="orchestration_intent_internal_maintenance_handoff",
        constraints=(
            "bounded_orchestration_handoff_only",
            "no_external_tool_direct_invocation",
            "admission_required_before_execution",
        ),
        steps=(
            task_executor.Step(
                step_id=1,
                kind="noop",
                payload=task_executor.NoopPayload(
                    note=json.dumps(
                        {
                            "intent_kind": intent.get("intent_kind"),
                            "recommended_venue": source_mapping.get("recommended_venue"),
                            "executability_classification": intent.get("executability_classification"),
                        },
                        sort_keys=True,
                    ),
                ),
            ),
        ),
        allow_epr=False,
        required_privileges=("orchestration_intent_handoff",),
    )


def _default_admission_context() -> task_admission.AdmissionContext:
    return task_admission.AdmissionContext(
        actor="orchestration_intent_fabric",
        mode="autonomous",
        node_id="sentientos_orchestration_handoff",
        vow_digest=None,
        doctrine_digest=None,
        now_utc_iso=_iso_utc_now(),
    )


def _default_admission_policy() -> task_admission.AdmissionPolicy:
    return task_admission.AdmissionPolicy(policy_version="orchestration_intent_handoff.v1")


def _staged_work_order_id(intent: Mapping[str, Any], created_at: str, *, prefix: str) -> str:
    canonical = json.dumps(
        {
            "created_at": created_at,
            "intent_id": str(intent.get("intent_id") or ""),
            "source_judgment": dict(intent.get("source_delegated_judgment") or {}),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{prefix}-wo-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _source_judgment_linkage_id(source_map: Mapping[str, Any]) -> str:
    canonical = json.dumps(dict(source_map), sort_keys=True, separators=(",", ":"))
    return f"jdg-link-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def append_codex_work_order_ledger(repo_root: Path, work_order: Mapping[str, Any]) -> Path:
    ledger_path = repo_root.resolve() / "glow/orchestration/codex_work_orders.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(work_order), sort_keys=True) + "\n")
    return ledger_path


def append_deep_research_work_order_ledger(repo_root: Path, work_order: Mapping[str, Any]) -> Path:
    ledger_path = repo_root.resolve() / "glow/orchestration/deep_research_work_orders.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(work_order), sort_keys=True) + "\n")
    return ledger_path


def _build_staged_external_work_order(
    intent: Mapping[str, Any],
    *,
    handoff_outcome: str,
    created_at: str | None = None,
    venue: str,
    schema_version: str,
    work_order_prefix: str,
    direct_invocation_boundary_key: str,
) -> dict[str, Any]:
    timestamp = created_at or _iso_utc_now()
    source = intent.get("source_delegated_judgment")
    source_map = source if isinstance(source, Mapping) else {}
    posture = str(intent.get("required_authority_posture") or "insufficient_context_blocked")
    if handoff_outcome == "blocked_by_operator_requirement":
        status = "blocked_operator_required"
    elif handoff_outcome == "blocked_by_insufficient_context":
        status = "blocked_insufficient_context"
    else:
        status = "staged"

    if status not in _STAGED_EXTERNAL_WORK_ORDER_STATUSES:
        status = "blocked_insufficient_context"

    work_order = {
        "schema_version": schema_version,
        "recorded_at": timestamp,
        "venue": venue,
        "work_order_id": _staged_work_order_id(intent, timestamp, prefix=work_order_prefix),
        "source_intent_id": str(intent.get("intent_id") or ""),
        "source_intent_kind": str(intent.get("intent_kind") or ""),
        "source_judgment_linkage": {
            "source_judgment_linkage_id": _source_judgment_linkage_id(source_map),
            "recommended_venue": str(source_map.get("recommended_venue") or ""),
            "judgment_kind": "execution_venue_recommendation",
            "escalation_classification": str(source_map.get("escalation_classification") or ""),
            "work_class": str(source_map.get("work_class") or ""),
            "next_move_posture": str(source_map.get("next_move_posture") or "hold"),
            "consolidation_expansion_posture": str(source_map.get("consolidation_expansion_posture") or "insufficient_context"),
        },
        "operator_requirements": {
            "requires_operator_approval": bool(intent.get("requires_operator_approval")),
            "required_authority_posture": posture,
            "operator_escalation_classification": str(source_map.get("escalation_classification") or ""),
        },
        "executability_classification": str(intent.get("executability_classification") or "blocked_insufficient_context"),
        "readiness_basis": dict(source_map.get("readiness_basis") or {}),
        "status": status,
        "staged_only": True,
        "requires_external_tool_or_operator_trigger": True,
        **_anti_sovereignty_payload(
            recommendation_only=False,
            diagnostic_only=False,
            does_not_invoke_external_tools=True,
            additional_fields={
                "non_authoritative": True,
                "decision_power": "none",
            },
        ),
    }
    work_order[direct_invocation_boundary_key] = True
    return work_order


def build_codex_staged_work_order(
    intent: Mapping[str, Any],
    *,
    handoff_outcome: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    return _build_staged_external_work_order(
        intent,
        handoff_outcome=handoff_outcome,
        created_at=created_at,
        venue="codex_implementation",
        schema_version="codex_staged_work_order.v1",
        work_order_prefix="codex",
        direct_invocation_boundary_key="does_not_invoke_codex_directly",
    )


def build_deep_research_staged_work_order(
    intent: Mapping[str, Any],
    *,
    handoff_outcome: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    return _build_staged_external_work_order(
        intent,
        handoff_outcome=handoff_outcome,
        created_at=created_at,
        venue="deep_research_audit",
        schema_version="deep_research_staged_work_order.v1",
        work_order_prefix="deep-research",
        direct_invocation_boundary_key="does_not_invoke_deep_research_directly",
    )


def _resolve_staged_external_work_order_lifecycle(
    repo_root: Path,
    intent: Mapping[str, Any],
    handoff: Mapping[str, Any],
    *,
    venue: str,
    ledger_relative_path: str,
    schema_version: str,
    direct_invocation_boundary_key: str,
) -> dict[str, Any]:
    root = repo_root.resolve()
    intent_id = str(intent.get("intent_id") or "")
    ledger_path = root / ledger_relative_path
    records = _read_jsonl(ledger_path)
    linked = [row for row in records if str(row.get("source_intent_id") or "") == intent_id]
    latest = linked[-1] if linked else None
    handoff_outcome = str(handoff.get("handoff_outcome") or "")

    if latest is None:
        lifecycle_state = "fragmented_unlinked_work_order_state"
    elif handoff_outcome == "blocked_by_operator_requirement":
        lifecycle_state = "blocked_operator_required"
    elif handoff_outcome == "blocked_by_insufficient_context":
        lifecycle_state = "blocked_insufficient_context"
    elif str(latest.get("status") or "") == "staged":
        lifecycle_state = "staged_cleanly"
    else:
        lifecycle_state = "fragmented_unlinked_work_order_state"

    if lifecycle_state not in _STAGED_EXTERNAL_LIFECYCLE_STATES:
        lifecycle_state = "fragmented_unlinked_work_order_state"

    lifecycle = {
        "schema_version": schema_version,
        "intent_id": intent_id,
        "venue": venue,
        "lifecycle_state": lifecycle_state,
        "work_order_present": latest is not None,
        "work_order_id": str(latest.get("work_order_id") or "") if isinstance(latest, Mapping) else None,
        "work_order_status": str(latest.get("status") or "") if isinstance(latest, Mapping) else None,
        "proof_artifact_path": ledger_relative_path,
        "not_directly_executable_here": True,
        "staged_only": True,
        "requires_external_tool_or_operator_trigger": True,
        "operator_requirement_state": {
            "requires_operator_approval": bool(intent.get("requires_operator_approval")),
            "required_authority_posture": str(intent.get("required_authority_posture") or ""),
        },
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
        ),
    }
    lifecycle[direct_invocation_boundary_key] = True
    return lifecycle


def resolve_codex_staged_work_order_lifecycle(
    repo_root: Path,
    intent: Mapping[str, Any],
    handoff: Mapping[str, Any],
) -> dict[str, Any]:
    return _resolve_staged_external_work_order_lifecycle(
        repo_root,
        intent,
        handoff,
        venue="codex_implementation",
        ledger_relative_path="glow/orchestration/codex_work_orders.jsonl",
        schema_version="codex_staged_lifecycle.v1",
        direct_invocation_boundary_key="does_not_invoke_codex_directly",
    )


def resolve_deep_research_staged_work_order_lifecycle(
    repo_root: Path,
    intent: Mapping[str, Any],
    handoff: Mapping[str, Any],
) -> dict[str, Any]:
    return _resolve_staged_external_work_order_lifecycle(
        repo_root,
        intent,
        handoff,
        venue="deep_research_audit",
        ledger_relative_path="glow/orchestration/deep_research_work_orders.jsonl",
        schema_version="deep_research_staged_lifecycle.v1",
        direct_invocation_boundary_key="does_not_invoke_deep_research_directly",
    )


def append_orchestration_handoff_ledger(repo_root: Path, handoff: Mapping[str, Any]) -> Path:
    ledger_path = repo_root.resolve() / "glow/orchestration/orchestration_handoffs.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(handoff), sort_keys=True) + "\n")
    return ledger_path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def build_handoff_execution_gap_map(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    return {
        "schema_version": "orchestration_handoff_execution_gap.v1",
        "path": [
            "delegated_judgment",
            "orchestration_intent",
            "orchestration_handoff",
            "task_admission",
            "task_executor",
        ],
        "existing_downstream_result_source": {
            "surface": "logs/task_executor.jsonl",
            "event": "task_result",
            "status_values": ["completed", "failed"],
        },
        "stable_linkage_keys": {
            "intent_to_handoff": "intent_id",
            "handoff_to_execution_task": "details.task_admission.task_id",
            "execution_task_to_result": "task_id",
        },
        "stop_point_without_resolution": "handoff_outcome=admitted_to_execution_substrate",
        "minimal_missing_linkage": (
            "resolve admitted handoff task_id against task_executor task_result and classify "
            "orchestration result state."
        ),
        "proof_surfaces": {
            "intent_ledger": "glow/orchestration/orchestration_intents.jsonl",
            "handoff_ledger": "glow/orchestration/orchestration_handoffs.jsonl",
            "admission_log": str(task_admission._resolve_admission_log_path().relative_to(root))
            if task_admission._resolve_admission_log_path().is_relative_to(root)
            else str(task_admission._resolve_admission_log_path()),
            "executor_log": str(Path(task_executor.LOG_PATH).relative_to(root))
            if Path(task_executor.LOG_PATH).is_relative_to(root)
            else str(Path(task_executor.LOG_PATH)),
        },
    }


def resolve_orchestration_result(
    repo_root: Path,
    handoff: Mapping[str, Any],
    *,
    executor_log_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    handoff_outcome = str(handoff.get("handoff_outcome") or "")
    details = handoff.get("details")
    detail_map = details if isinstance(details, Mapping) else {}
    task_admission_details = detail_map.get("task_admission")
    admission_map = task_admission_details if isinstance(task_admission_details, Mapping) else {}
    task_id = str(admission_map.get("task_id") or "")
    log_path = executor_log_path or Path(task_executor.LOG_PATH)
    matching_rows = [row for row in _read_jsonl(log_path) if str(row.get("task_id") or "") == task_id]
    task_result_rows = [row for row in matching_rows if str(row.get("event") or "") == "task_result"]

    state = "handoff_not_admitted"
    execution_observed = False
    loop_closed = False

    if handoff_outcome == "admitted_to_execution_substrate":
        if not task_id:
            state = "execution_result_missing"
        elif task_result_rows:
            execution_observed = True
            latest = task_result_rows[-1]
            status = str(latest.get("status") or "")
            if status == "completed":
                state = "execution_succeeded"
                loop_closed = True
            elif status == "failed":
                state = "execution_failed"
                loop_closed = True
            else:
                state = "execution_result_missing"
        elif matching_rows:
            state = "execution_still_pending"
        else:
            state = "handoff_admitted_pending_result"

    if state not in _EXECUTION_RESULT_STATES:
        state = "execution_result_missing"

    intent_ref = dict(handoff.get("intent_ref") or {})
    codex_staged_lifecycle = None
    deep_research_staged_lifecycle = None
    if str(intent_ref.get("intent_kind") or "") == "codex_work_order":
        codex_staged_lifecycle = resolve_codex_staged_work_order_lifecycle(
            root,
            {
                "intent_id": str(intent_ref.get("intent_id") or ""),
                "required_authority_posture": str(detail_map.get("required_authority_posture") or ""),
                "requires_operator_approval": bool(detail_map.get("requires_operator_approval")),
            },
            handoff,
        )
    if str(intent_ref.get("intent_kind") or "") == "deep_research_work_order":
        deep_research_staged_lifecycle = resolve_deep_research_staged_work_order_lifecycle(
            root,
            {
                "intent_id": str(intent_ref.get("intent_id") or ""),
                "required_authority_posture": str(detail_map.get("required_authority_posture") or ""),
                "requires_operator_approval": bool(detail_map.get("requires_operator_approval")),
            },
            handoff,
        )

    return {
        "schema_version": "orchestration_result_resolution.v1",
        "resolved_at": _iso_utc_now(),
        "intent_ref": intent_ref,
        "handoff_outcome": handoff_outcome,
        "orchestration_result_state": state,
        "loop_closed": loop_closed,
        "execution_observed": execution_observed,
        "execution_task_ref": {
            "task_id": task_id or None,
            "executor_log_path": str(log_path.relative_to(root)) if log_path.is_relative_to(root) else str(log_path),
        },
        "result_evidence": {
            "task_rows_seen": len(matching_rows),
            "task_result_rows_seen": len(task_result_rows),
        },
        "codex_staged_lifecycle": codex_staged_lifecycle,
        "deep_research_staged_lifecycle": deep_research_staged_lifecycle,
    }


def derive_orchestration_outcome_review(
    repo_root: Path,
    *,
    window_size: int = 10,
    executor_log_path: Path | None = None,
) -> dict[str, Any]:
    """Derive a bounded retrospective review over recent orchestration outcomes."""

    root = repo_root.resolve()
    intents = _read_jsonl(root / "glow/orchestration/orchestration_intents.jsonl")
    handoffs = _read_jsonl(root / "glow/orchestration/orchestration_handoffs.jsonl")
    intent_ids = {str(row.get("intent_id") or "") for row in intents}
    scoped_handoffs: list[dict[str, Any]] = []
    for handoff in handoffs:
        intent_ref = handoff.get("intent_ref")
        intent_ref_map = intent_ref if isinstance(intent_ref, Mapping) else {}
        intent_id = str(intent_ref_map.get("intent_id") or "")
        if intent_id and intent_id in intent_ids:
            scoped_handoffs.append(handoff)

    recent_handoffs = scoped_handoffs[-max(0, window_size) :] if window_size > 0 else []
    recent_resolutions = [
        resolve_orchestration_result(root, handoff, executor_log_path=executor_log_path)
        for handoff in recent_handoffs
    ]

    outcome_counts = {
        "execution_succeeded": 0,
        "execution_failed": 0,
        "handoff_admitted_pending_result": 0,
        "execution_still_pending": 0,
        "execution_result_missing": 0,
        "handoff_not_admitted": 0,
    }
    blocked_handoffs = 0
    admitted_handoffs = 0
    for idx, resolution in enumerate(recent_resolutions):
        state = str(resolution.get("orchestration_result_state") or "execution_result_missing")
        if state not in outcome_counts:
            state = "execution_result_missing"
        outcome_counts[state] += 1

        handoff_outcome = str(recent_handoffs[idx].get("handoff_outcome") or "")
        if handoff_outcome in {
            "blocked_by_admission",
            "blocked_by_operator_requirement",
            "blocked_by_insufficient_context",
            "execution_target_unavailable",
        }:
            blocked_handoffs += 1
        if handoff_outcome == "admitted_to_execution_substrate":
            admitted_handoffs += 1

    records_considered = len(recent_resolutions)
    success_count = outcome_counts["execution_succeeded"]
    failure_count = outcome_counts["execution_failed"]
    pending_count = (
        outcome_counts["handoff_admitted_pending_result"]
        + outcome_counts["execution_still_pending"]
        + outcome_counts["execution_result_missing"]
    )
    block_ratio = (blocked_handoffs / records_considered) if records_considered else 0.0
    success_ratio = (success_count / records_considered) if records_considered else 0.0
    failure_ratio = (failure_count / admitted_handoffs) if admitted_handoffs else 0.0
    pending_ratio = (pending_count / admitted_handoffs) if admitted_handoffs else 0.0

    blocked_heavy = blocked_handoffs >= 2 and block_ratio >= 0.6
    failure_heavy = admitted_handoffs >= 3 and failure_count >= 2 and failure_ratio >= 0.5
    stall_heavy = admitted_handoffs >= 3 and pending_count >= 2 and pending_ratio >= 0.5

    classification = "insufficient_history"
    if records_considered >= 3:
        if blocked_heavy:
            classification = "handoff_block_heavy"
        elif failure_heavy:
            classification = "execution_failure_heavy"
        elif stall_heavy:
            classification = "pending_stall_pattern"
        elif success_count >= 2 and success_ratio >= 0.6:
            classification = "clean_recent_orchestration"
        else:
            classification = "mixed_orchestration_stress"

    if classification not in _ORCHESTRATION_REVIEW_CLASSES:
        classification = "mixed_orchestration_stress"

    return {
        "schema_version": "orchestration_outcome_review.v1",
        "review_kind": "orchestration_outcome_retrospective",
        "review_classification": classification,
        "window_size": max(0, window_size),
        "records_considered": records_considered,
        "recent_outcome_counts": outcome_counts,
        "condition_flags": {
            "blocked_heavy": blocked_heavy,
            "failure_heavy": failure_heavy,
            "stall_heavy": stall_heavy,
        },
        "summary": {
            "recent_pattern": "healthy_bounded_orchestration"
            if classification == "clean_recent_orchestration"
            else "orchestration_stress_or_uncertainty",
            "diagnostic_summary": "bounded retrospective review derived from existing internal orchestration artifacts only",
        },
        "artifacts_read": {
            "intent_ledger": "glow/orchestration/orchestration_intents.jsonl",
            "handoff_ledger": "glow/orchestration/orchestration_handoffs.jsonl",
            "executor_log": str((executor_log_path or Path(task_executor.LOG_PATH)).relative_to(root))
            if (executor_log_path or Path(task_executor.LOG_PATH)).is_relative_to(root)
            else str(executor_log_path or Path(task_executor.LOG_PATH)),
        },
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "review_only": True,
                "does_not_change_admission_or_execution_authority": True,
            },
        ),
    }


def derive_orchestration_attention_recommendation(
    outcome_review: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive bounded operator-attention recommendation from orchestration outcome review only."""

    review_classification = str(outcome_review.get("review_classification") or "insufficient_history")
    records_considered = int(outcome_review.get("records_considered") or 0)
    condition_flags_raw = outcome_review.get("condition_flags")
    condition_flags = condition_flags_raw if isinstance(condition_flags_raw, Mapping) else {}
    blocked_heavy = bool(condition_flags.get("blocked_heavy"))
    failure_heavy = bool(condition_flags.get("failure_heavy"))
    stall_heavy = bool(condition_flags.get("stall_heavy"))
    recent_counts_raw = outcome_review.get("recent_outcome_counts")
    recent_outcome_counts = recent_counts_raw if isinstance(recent_counts_raw, Mapping) else {}
    handoff_not_admitted = int(recent_outcome_counts.get("handoff_not_admitted") or 0)
    light_block_pattern = handoff_not_admitted >= 1 and not blocked_heavy

    recommendation = "insufficient_context"
    rationale = "insufficient_orchestration_history_for_confident_attention_guidance"

    if review_classification == "clean_recent_orchestration":
        recommendation = "none"
        rationale = "recent_internal_orchestration_outcomes_are_clean_and_loop_closure_is_healthy"
    elif review_classification == "handoff_block_heavy" or blocked_heavy:
        recommendation = "inspect_handoff_blocks"
        rationale = "recent_history_shows_block_heavy_internal_handoff_behavior"
    elif review_classification == "execution_failure_heavy" or failure_heavy:
        recommendation = "inspect_execution_failures"
        rationale = "recent_history_shows_execution_failure_heavy_pattern_after_admission"
    elif review_classification == "pending_stall_pattern" or stall_heavy:
        recommendation = "inspect_pending_stall"
        rationale = "recent_history_shows_pending_or_missing_result_stall_pattern"
    elif review_classification == "mixed_orchestration_stress":
        recommendation = "review_mixed_orchestration_stress"
        rationale = "recent_history_shows_mixed_orchestration_stress_needing_human_interpretation"
    elif review_classification == "insufficient_history":
        recommendation = "insufficient_context"
        rationale = "insufficient_recent_orchestration_history_for_specific_attention_recommendation"
    elif light_block_pattern and records_considered >= 3 and review_classification not in {"clean_recent_orchestration"}:
        recommendation = "observe"
        rationale = "light_non_failure_handoff_block_pattern_detected_observe_before_deeper_intervention"

    if (
        light_block_pattern
        and review_classification == "mixed_orchestration_stress"
        and recommendation == "review_mixed_orchestration_stress"
    ):
        recommendation = "observe"
        rationale = "light_non_failure_handoff_block_pattern_detected_observe_before_deeper_intervention"

    if recommendation not in _ORCHESTRATION_ATTENTION_RECOMMENDATIONS:
        recommendation = "insufficient_context"
        rationale = "unrecognized_review_pattern_defaulted_to_insufficient_context"

    return {
        "schema_version": "orchestration_attention_recommendation.v1",
        "source": "orchestration_outcome_review",
        "review_ref": {
            "schema_version": str(outcome_review.get("schema_version") or ""),
            "review_kind": str(outcome_review.get("review_kind") or ""),
            "review_classification": review_classification,
        },
        "operator_attention_recommendation": recommendation,
        "basis": {
            "records_considered": records_considered,
            "condition_flags": {
                "blocked_heavy": blocked_heavy,
                "failure_heavy": failure_heavy,
                "stall_heavy": stall_heavy,
                "light_block_pattern": light_block_pattern,
            },
            "recent_outcome_counts": {
                "execution_succeeded": int(recent_outcome_counts.get("execution_succeeded") or 0),
                "execution_failed": int(recent_outcome_counts.get("execution_failed") or 0),
                "handoff_admitted_pending_result": int(recent_outcome_counts.get("handoff_admitted_pending_result") or 0),
                "execution_still_pending": int(recent_outcome_counts.get("execution_still_pending") or 0),
                "execution_result_missing": int(recent_outcome_counts.get("execution_result_missing") or 0),
                "handoff_not_admitted": handoff_not_admitted,
            },
            "rationale": rationale,
            "derived_from_existing_signals_only": [
                "orchestration_outcome_review.review_classification",
                "orchestration_outcome_review.condition_flags",
                "orchestration_outcome_review.recent_outcome_counts",
            ],
        },
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
        ),
    }


def executable_handoff_map() -> dict[str, Any]:
    return {
        "intent_kind_to_handoff": {
            "internal_maintenance_execution": {
                "execution_target": "task_admission_executor",
                "executability_classification": "executable_now",
                "admission_surface": "task_admission.admit",
                "handoff_path_status": "operational",
            },
            "codex_work_order": {
                "execution_target": "no_execution_target_yet",
                "executability_classification": "stageable_external_work_order",
                "admission_surface": "none",
                "handoff_path_status": "staged_only",
            },
            "deep_research_work_order": {
                "execution_target": "no_execution_target_yet",
                "executability_classification": "stageable_external_work_order",
                "admission_surface": "none",
                "handoff_path_status": "staged_only",
            },
            "operator_review_request": {
                "execution_target": "no_execution_target_yet",
                "executability_classification": "blocked_operator_required",
                "admission_surface": "operator-only",
                "handoff_path_status": "blocked_or_staged",
            },
            "hold_no_action": {
                "execution_target": "no_execution_target_yet",
                "executability_classification": "no_action_recommended",
                "admission_surface": "none",
                "handoff_path_status": "not_applicable",
            },
        },
        "known_named_targets_without_handoff_path": [
            "mutation_router",
            "federation_canonical_execution",
            "external_tool_placeholder",
        ],
    }


def admit_orchestration_intent(
    repo_root: Path,
    intent: Mapping[str, Any],
    *,
    admission_context: task_admission.AdmissionContext | None = None,
    admission_policy: task_admission.AdmissionPolicy | None = None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    missing_fields = _validate_handoff_minimum_fields(intent)
    execution_target = str(intent.get("execution_target") or "")
    executability = str(intent.get("executability_classification") or "")
    authority_posture = str(intent.get("required_authority_posture") or "")

    outcome = "staged_only"
    details: dict[str, Any] = {
        "intent_id": str(intent.get("intent_id") or ""),
        "intent_kind": str(intent.get("intent_kind") or ""),
        "execution_target": execution_target,
        "executability_classification": executability,
        "required_authority_posture": authority_posture,
        "requires_operator_approval": bool(intent.get("requires_operator_approval")),
    }

    if missing_fields:
        outcome = "blocked_by_insufficient_context"
        details["missing_required_fields"] = missing_fields
    elif executability == "blocked_operator_required" or authority_posture in {"operator_approval_required", "operator_priority_required"}:
        outcome = "blocked_by_operator_requirement"
    elif executability == "blocked_insufficient_context" or authority_posture == "insufficient_context_blocked":
        outcome = "blocked_by_insufficient_context"
    elif executability != "executable_now":
        outcome = "staged_only"
    elif execution_target != "task_admission_executor":
        outcome = "execution_target_unavailable"
    else:
        ctx = admission_context or _default_admission_context()
        policy = admission_policy or _default_admission_policy()
        task = _build_internal_maintenance_task(intent)
        decision = task_admission.admit(task, ctx, policy)
        task_admission._log_admission_event(decision, task, ctx, policy)
        details["task_admission"] = {
            "task_id": task.task_id,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "policy_version": decision.policy_version,
            "constraints": decision.constraints,
            "log_path": str(task_admission._resolve_admission_log_path().relative_to(root))
            if task_admission._resolve_admission_log_path().is_relative_to(root)
            else str(task_admission._resolve_admission_log_path()),
        }
        outcome = "admitted_to_execution_substrate" if decision.allowed else "blocked_by_admission"

    if outcome not in _HANDOFF_OUTCOMES:
        outcome = "blocked_by_insufficient_context"

    codex_work_order_record = None
    if str(intent.get("intent_kind") or "") == "codex_work_order":
        codex_work_order_record = build_codex_staged_work_order(intent, handoff_outcome=outcome)
        codex_path = append_codex_work_order_ledger(root, codex_work_order_record)
        details["codex_work_order_ref"] = {
            "work_order_id": codex_work_order_record["work_order_id"],
            "ledger_path": str(codex_path.relative_to(root)),
            "status": codex_work_order_record["status"],
            "staged_only": True,
            "does_not_invoke_codex_directly": True,
            "requires_external_tool_or_operator_trigger": True,
        }
    if str(intent.get("intent_kind") or "") == "deep_research_work_order":
        deep_research_work_order_record = build_deep_research_staged_work_order(intent, handoff_outcome=outcome)
        deep_research_path = append_deep_research_work_order_ledger(root, deep_research_work_order_record)
        details["deep_research_work_order_ref"] = {
            "work_order_id": deep_research_work_order_record["work_order_id"],
            "ledger_path": str(deep_research_path.relative_to(root)),
            "status": deep_research_work_order_record["status"],
            "staged_only": True,
            "does_not_invoke_deep_research_directly": True,
            "requires_external_tool_or_operator_trigger": True,
        }

    handoff_record = {
        "schema_version": "orchestration_handoff.v1",
        "recorded_at": _iso_utc_now(),
        "handoff_outcome": outcome,
        "intent_ref": {
            "intent_id": str(intent.get("intent_id") or ""),
            "intent_kind": str(intent.get("intent_kind") or ""),
        },
        "details": details,
        **_anti_sovereignty_payload(
            recommendation_only=False,
            diagnostic_only=False,
            does_not_invoke_external_tools=True,
        ),
        "does_not_execute_task_directly": True,
    }
    handoff_ledger_path = append_orchestration_handoff_ledger(root, handoff_record)
    return {
        **handoff_record,
        "ledger_path": str(handoff_ledger_path.relative_to(root)),
    }
