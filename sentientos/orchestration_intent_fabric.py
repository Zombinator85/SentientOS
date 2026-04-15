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
        "non_authoritative": True,
        "recommendation_only": False,
        "diagnostic_only": False,
        "staged_handoff_only": executability != "executable_now",
        "does_not_invoke_external_tools": True,
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

    return {
        "schema_version": "orchestration_result_resolution.v1",
        "resolved_at": _iso_utc_now(),
        "intent_ref": dict(handoff.get("intent_ref") or {}),
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
    }

    if missing_fields:
        outcome = "blocked_by_insufficient_context"
        details["missing_required_fields"] = missing_fields
    elif executability != "executable_now":
        outcome = "staged_only"
    elif authority_posture != "no_additional_operator_approval_required":
        outcome = "blocked_by_operator_requirement"
        details["required_authority_posture"] = authority_posture
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

    handoff_record = {
        "schema_version": "orchestration_handoff.v1",
        "recorded_at": _iso_utc_now(),
        "handoff_outcome": outcome,
        "intent_ref": {
            "intent_id": str(intent.get("intent_id") or ""),
            "intent_kind": str(intent.get("intent_kind") or ""),
        },
        "details": details,
        "non_authoritative": True,
        "does_not_execute_task_directly": True,
        "does_not_invoke_external_tools": True,
    }
    handoff_ledger_path = append_orchestration_handoff_ledger(root, handoff_record)
    return {
        **handoff_record,
        "ledger_path": str(handoff_ledger_path.relative_to(root)),
    }
