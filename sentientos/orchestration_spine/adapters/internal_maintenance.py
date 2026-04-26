from __future__ import annotations

"""Internal-maintenance adapter primitives for orchestration handoff.

This module is adapter-owned and substrate-specific. It shapes maintenance tasks
and default admission inputs, while kernel authority decisions remain in
``sentientos.orchestration_intent_fabric``.

Adapter responsibility groups in this module:
- maintenance task materialization into ``task_executor.Task`` payloads
- admission/log handshake helpers for ``task_admission`` substrate calls
- task-executor result linkage helpers over raw jsonl substrate evidence

These helpers must never redefine canonical intent identity, legal/illegal
meaning, linkage authority, or closure semantics; those remain kernel-owned.
"""

import json
from pathlib import Path
from typing import Any, Callable, Mapping

import task_admission
import task_executor

ADAPTER_GROUP_MAINTENANCE_TASK_MATERIALIZATION = "maintenance_task_materialization"
ADAPTER_GROUP_ADMISSION_HANDSHAKE = "admission_log_handshake"
ADAPTER_GROUP_EXECUTOR_RESULT_LINKAGE = "executor_result_linkage"
ADAPTER_GROUPS = (
    ADAPTER_GROUP_MAINTENANCE_TASK_MATERIALIZATION,
    ADAPTER_GROUP_ADMISSION_HANDSHAKE,
    ADAPTER_GROUP_EXECUTOR_RESULT_LINKAGE,
)


def build_internal_maintenance_task(intent: Mapping[str, Any]) -> task_executor.Task:
    """Materialize bounded internal-maintenance work into executor substrate shape.

    Consumes already-derived orchestration intent evidence and emits a concrete
    ``task_executor.Task`` compatible payload. This adapter does not decide
    authority, legitimacy, or lifecycle outcomes.
    """
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
    """Provide adapter-local default admission context for substrate invocation.

    This is wiring convenience for ``task_admission``; canonical actor/identity
    authority still resides in the orchestration kernel/facade contract.
    """
    return task_admission.AdmissionContext(
        actor="orchestration_intent_fabric",
        mode="autonomous",
        node_id="sentientos_orchestration_handoff",
        vow_digest=None,
        doctrine_digest=None,
        now_utc_iso=now_utc_iso,
    )


def default_admission_policy() -> task_admission.AdmissionPolicy:
    """Return the bounded admission policy handle used for handoff calls."""
    return task_admission.AdmissionPolicy(policy_version="orchestration_intent_handoff.v1")


def admit_internal_maintenance_intent(
    *,
    intent: Mapping[str, Any],
    root: Path,
    admission_context: task_admission.AdmissionContext | None,
    admission_policy: task_admission.AdmissionPolicy | None,
    now_utc_iso: str,
) -> dict[str, Any]:
    """Bridge internal-maintenance intent into admission substrate + log evidence.

    Shapes substrate call arguments, performs admission invocation/logging, and
    returns a normalized evidence map for upstream orchestration reporting.
    """
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
    """Resolve executor-side evidence rows linked to an admitted handoff task.

    Consumes handoff details plus raw executor jsonl rows and returns linkage
    evidence only; it does not establish canonical linkage semantics.
    """
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


__all__ = [
    "ADAPTER_GROUP_MAINTENANCE_TASK_MATERIALIZATION",
    "ADAPTER_GROUP_ADMISSION_HANDSHAKE",
    "ADAPTER_GROUP_EXECUTOR_RESULT_LINKAGE",
    "ADAPTER_GROUPS",
    "build_internal_maintenance_task",
    "default_admission_context",
    "default_admission_policy",
    "admit_internal_maintenance_intent",
    "resolve_task_executor_result_linkage",
]
