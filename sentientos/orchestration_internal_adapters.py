from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

import task_admission
import task_executor


def build_internal_maintenance_task(intent: Mapping[str, Any]) -> task_executor.Task:
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


def default_admission_context(now_utc_iso: str) -> task_admission.AdmissionContext:
    return task_admission.AdmissionContext(
        actor="orchestration_intent_fabric",
        mode="autonomous",
        node_id="sentientos_orchestration_handoff",
        vow_digest=None,
        doctrine_digest=None,
        now_utc_iso=now_utc_iso,
    )


def default_admission_policy() -> task_admission.AdmissionPolicy:
    return task_admission.AdmissionPolicy(policy_version="orchestration_intent_handoff.v1")


def admit_internal_maintenance_intent(
    *,
    intent: Mapping[str, Any],
    root: Path,
    admission_context: task_admission.AdmissionContext | None,
    admission_policy: task_admission.AdmissionPolicy | None,
    now_utc_iso: str,
) -> dict[str, Any]:
    ctx = admission_context or default_admission_context(now_utc_iso)
    policy = admission_policy or default_admission_policy()
    task = build_internal_maintenance_task(intent)
    decision = task_admission.admit(task, ctx, policy)
    task_admission._log_admission_event(decision, task, ctx, policy)
    log_path = task_admission._resolve_admission_log_path()
    return {
        "task_id": task.task_id,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "policy_version": decision.policy_version,
        "constraints": decision.constraints,
        "log_path": str(log_path.relative_to(root)) if log_path.is_relative_to(root) else str(log_path),
    }


def resolve_task_executor_result_linkage(
    *,
    handoff: Mapping[str, Any],
    executor_log_path: Path,
    read_jsonl: Callable[[Path], list[dict[str, Any]]],
) -> dict[str, Any]:
    details = handoff.get("details")
    detail_map = details if isinstance(details, Mapping) else {}
    task_admission_details = detail_map.get("task_admission")
    admission_map = task_admission_details if isinstance(task_admission_details, Mapping) else {}
    task_id = str(admission_map.get("task_id") or "")
    matching_rows = [row for row in read_jsonl(executor_log_path) if str(row.get("task_id") or "") == task_id]
    task_result_rows = [row for row in matching_rows if str(row.get("event") or "") == "task_result"]
    return {
        "task_id": task_id,
        "task_rows": matching_rows,
        "task_result_rows": task_result_rows,
    }
