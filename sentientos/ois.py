from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping

import control_plane.policy
import task_admission
import task_executor
from logging_config import get_log_path
from log_utils import append_json, read_json
from sentientos.external_adapters import list_adapters
from sentientos.governance.routine_delegation import DEFAULT_LOG_PATH as ROUTINE_LOG_PATH
from sentientos.governance.routine_delegation import RoutineRegistry
from sentientos.governance.semantic_habit_class import DEFAULT_LOG_PATH as SEMANTIC_CLASS_LOG_PATH
from sentientos.system_identity import compute_system_identity_digest

INTROSPECTION_LOG_PATH = get_log_path(
    "introspection_access.jsonl",
    "SENTIENTOS_INTROSPECTION_ACCESS_LOG",
)


def log_introspection_access(view: str, *, detail: Mapping[str, object] | None = None) -> None:
    entry: dict[str, object] = {
        "event": "introspection_access",
        "authority": "none",
        "side_effects": "none",
        "view": view,
    }
    if detail:
        entry["detail"] = dict(detail)
    append_json(INTROSPECTION_LOG_PATH, entry)


def build_system_overview() -> dict[str, object]:
    tasks = _summarize_tasks(_read_audit_log(Path(task_executor.LOG_PATH)))
    routines = _summarize_routines(_read_audit_log(Path(ROUTINE_LOG_PATH)))
    habits = _summarize_semantic_habits(_read_audit_log(Path(SEMANTIC_CLASS_LOG_PATH)))
    adapters = _summarize_adapters()
    privilege = _summarize_privilege_posture()
    return {
        "view": "system_state_overview",
        "active_tasks": tasks,
        "delegated_routines": routines,
        "semantic_habit_classes": habits,
        "active_adapters": adapters,
        "privilege_posture": privilege,
    }


def build_execution_trace(limit: int = 10) -> dict[str, object]:
    task_entries = _read_audit_log(Path(task_executor.LOG_PATH))
    routine_entries = _read_audit_log(Path(ROUTINE_LOG_PATH))
    admission_entries = _read_audit_log(Path(task_admission.ADMISSION_LOG_PATH))
    admission_lookup = _index_by_task(admission_entries)

    task_executions = _collect_task_executions(task_entries, admission_lookup)
    routine_executions = _collect_routine_executions(routine_entries)

    combined = sorted(
        [*task_executions, *routine_executions],
        key=lambda item: float(item.get("timestamp", 0.0)),
        reverse=True,
    )

    return {
        "view": "execution_trace",
        "limit": limit,
        "executions": combined[:limit],
    }


def build_explanation(
    *,
    task_id: str | None = None,
    routine_id: str | None = None,
) -> dict[str, object]:
    if task_id:
        return _explain_task(task_id)
    if routine_id:
        return _explain_routine(routine_id)
    return {
        "view": "explanation",
        "error": "task_id or routine_id required",
    }


def build_simulation(
    *,
    task_payload: Mapping[str, object] | None = None,
    routine_id: str | None = None,
    adapter_id: str | None = None,
    adapter_action: str | None = None,
) -> dict[str, object]:
    if task_payload is not None:
        return _simulate_task(task_payload)
    if routine_id is not None:
        return _simulate_routine(routine_id)
    if adapter_id is not None and adapter_action is not None:
        return _simulate_adapter(adapter_id, adapter_action)
    return {
        "view": "simulation",
        "error": "task_payload, routine_id, or adapter_id+adapter_action required",
    }


def _read_audit_log(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        return read_json(path)
    except Exception:
        return []


def _summarize_tasks(entries: Iterable[Mapping[str, object]]) -> dict[str, object]:
    state: dict[str, dict[str, object]] = {}
    for entry in entries:
        task_id = entry.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            continue
        task_state = state.setdefault(task_id, {"has_steps": False, "blocked": False})
        event = entry.get("event")
        if event == "task_result":
            task_state["terminal_status"] = entry.get("status")
            task_state["terminal_error"] = entry.get("error")
            continue
        if event == "exhaustion":
            task_state["blocked"] = True
            task_state["block_reason"] = entry.get("reason")
            task_state["block_type"] = "exhaustion"
            continue
        if event == "unknown_prerequisite":
            status = entry.get("status")
            if status in {"authority-required", "impossible", "unknown"}:
                task_state["blocked"] = True
                task_state["block_reason"] = entry.get("reason")
                task_state["block_type"] = "prerequisite"
            continue
        if event == "epr_action" and entry.get("status") == "blocked":
            task_state["blocked"] = True
            task_state["block_reason"] = entry.get("error")
            task_state["block_type"] = "approval"
            continue
        if "step_id" in entry:
            task_state["has_steps"] = True

    running: list[dict[str, object]] = []
    blocked: list[dict[str, object]] = []
    completed: list[dict[str, object]] = []

    for task_id, details in state.items():
        terminal_status = details.get("terminal_status")
        if terminal_status in {"completed", "failed"}:
            completed.append({
                "task_id": task_id,
                "status": terminal_status,
                "error": details.get("terminal_error"),
            })
        elif details.get("blocked"):
            blocked.append({
                "task_id": task_id,
                "reason": details.get("block_reason"),
                "block_type": details.get("block_type"),
            })
        elif details.get("has_steps"):
            running.append({"task_id": task_id})

    return {
        "running": running,
        "blocked": blocked,
        "completed": completed,
    }


def _summarize_routines(entries: Iterable[Mapping[str, object]]) -> dict[str, object]:
    registry = RoutineRegistry()
    routines = registry.list_routines()

    last_outcome: dict[str, str] = {}
    conflict_prompted: set[str] = set()

    for entry in entries:
        event = entry.get("event")
        if event == "routine_evaluation":
            routine_id = entry.get("routine_id")
            outcome = entry.get("outcome")
            if isinstance(routine_id, str) and isinstance(outcome, str):
                last_outcome[routine_id] = outcome
        if event == "routine_conflict_prompt":
            routines_payload = entry.get("routines")
            if isinstance(routines_payload, list):
                for routine in routines_payload:
                    routine_id = routine.get("routine_id") if isinstance(routine, Mapping) else None
                    if isinstance(routine_id, str):
                        conflict_prompted.add(routine_id)

    grouped: dict[str, list[dict[str, object]]] = {"enabled": [], "paused": [], "conflicted": []}

    for routine in routines:
        outcome = last_outcome.get(routine.routine_id)
        status = "enabled"
        if routine.routine_id in conflict_prompted or outcome == "conflict_suppressed":
            status = "conflicted"
        elif outcome == "conflict_paused":
            status = "paused"
        grouped[status].append({
            "routine_id": routine.routine_id,
            "trigger": routine.trigger_description,
            "action": routine.action_description,
            "scope": list(routine.scope),
        })

    return grouped


def _summarize_semantic_habits(entries: Iterable[Mapping[str, object]]) -> list[str]:
    active: dict[str, bool] = {}
    for entry in entries:
        event = entry.get("event")
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        if event in {"semantic_class_created", "semantic_class_approved"}:
            active[name] = True
        elif event == "semantic_class_revoked":
            active.pop(name, None)
    return sorted(active)


def _summarize_adapters() -> list[dict[str, object]]:
    adapters = []
    for adapter_id, adapter_cls in list_adapters().items():
        metadata = adapter_cls.metadata
        adapters.append({
            "adapter_id": adapter_id,
            "scope": metadata.scope,
            "capabilities": list(metadata.capabilities),
            "requires_privilege": metadata.requires_privilege,
            "external_effects": metadata.external_effects,
            "reversibility": metadata.reversibility,
        })
    return adapters


def _summarize_privilege_posture() -> dict[str, object]:
    admission_policy = _default_admission_policy()
    identity = compute_system_identity_digest(
        admission_policy=admission_policy,
        control_policy=control_plane.policy.load_policy(),
        closure_limits=task_executor.load_closure_limits(),
        metadata={
            "policy_source": "default_admission_policy",
            "policy_version": admission_policy.policy_version,
        },
    )
    components = identity.get("components", {})
    privilege_surface = components.get("privilege_surface", {})
    governance = components.get("governance", {})
    execution = components.get("execution", {})
    return {
        "policy_source": "default_admission_policy",
        "admission_policy": governance.get("admission", {}),
        "control_policy": governance.get("authorization", {}),
        "privilege_surface": privilege_surface,
        "closure_limits": execution.get("exhaustion_limits", {}),
        "mode": os.getenv("SENTIENTOS_MODE", "DEFAULT"),
    }


def _index_by_task(entries: Iterable[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    for entry in entries:
        task_id = entry.get("task_id")
        if isinstance(task_id, str):
            lookup[task_id] = dict(entry)
    return lookup


def _collect_task_executions(
    entries: Iterable[Mapping[str, object]],
    admission_lookup: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    tasks: dict[str, dict[str, object]] = {}
    for entry in entries:
        task_id = entry.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            continue
        record = tasks.setdefault(task_id, {
            "task_id": task_id,
            "timestamp": entry.get("timestamp", 0.0),
            "adapters": [],
            "epr_actions": [],
            "authority_boundaries": [],
            "failures": [],
        })
        record["timestamp"] = max(float(record.get("timestamp", 0.0) or 0.0), float(entry.get("timestamp", 0.0) or 0.0))
        event = entry.get("event")
        if event == "task_result":
            record["status"] = entry.get("status")
            if entry.get("error"):
                record["failures"].append({
                    "reason": entry.get("error"),
                    "type": "task_result",
                })
        elif event == "epr_action":
            record["epr_actions"].append({
                "action_id": entry.get("action_id"),
                "status": entry.get("status"),
                "authority_impact": entry.get("authority_impact"),
                "reversibility": entry.get("reversibility"),
            })
            if entry.get("status") == "blocked":
                record["authority_boundaries"].append({
                    "type": "missing_approval",
                    "detail": entry.get("error"),
                })
        elif event == "unknown_prerequisite":
            status = entry.get("status")
            boundary_type = "unmet_prerequisites"
            if status == "authority-required":
                boundary_type = "missing_approval"
            record["authority_boundaries"].append({
                "type": boundary_type,
                "detail": entry.get("reason"),
                "status": status,
            })
        elif event == "exhaustion":
            record["failures"].append({
                "reason": entry.get("reason"),
                "type": "exhaustion",
                "exhaustion_type": entry.get("exhaustion_type"),
            })
        elif entry.get("kind") == "adapter":
            artifacts = entry.get("artifacts")
            if isinstance(artifacts, Mapping):
                record["adapters"].append({
                    "adapter_id": artifacts.get("adapter_id"),
                    "action": artifacts.get("adapter_action"),
                })

    executions: list[dict[str, object]] = []
    for task_id, record in tasks.items():
        admission = admission_lookup.get(task_id)
        record["trigger"] = {
            "source": admission.get("actor") if admission else None,
            "mode": admission.get("mode") if admission else None,
            "policy_version": admission.get("policy_version") if admission else None,
        }
        record["type"] = "task"
        executions.append(record)
    return executions


def _collect_routine_executions(entries: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    executions: list[dict[str, object]] = []
    for entry in entries:
        event = entry.get("event")
        if event != "delegated_execution":
            continue
        executions.append({
            "type": "routine",
            "routine_id": entry.get("routine_id"),
            "timestamp": entry.get("timestamp", 0.0),
            "trigger": {
                "approval_id": entry.get("approval_id"),
                "trigger_evaluation": entry.get("trigger_evaluation"),
            },
            "action": entry.get("action_taken"),
            "outcome": entry.get("outcome"),
            "scope_adherence": entry.get("scope_adherence"),
            "authority_boundaries": (
                [{"type": "scope_violations", "detail": "scope_adherence_false"}]
                if entry.get("scope_adherence") is False
                else []
            ),
            "failures": (
                [{"type": "routine_failure", "reason": entry.get("outcome")}]
                if entry.get("outcome") == "failed"
                else []
            ),
            "adapters": [],
            "epr_actions": [],
        })
    return executions


def _explain_task(task_id: str) -> dict[str, object]:
    admissions = _read_audit_log(Path(task_admission.ADMISSION_LOG_PATH))
    executor_entries = _read_audit_log(Path(task_executor.LOG_PATH))
    facts: list[dict[str, object]] = []

    for entry in admissions:
        if entry.get("task_id") != task_id:
            continue
        if entry.get("event") == "TASK_ADMISSION_DENIED":
            reason = entry.get("reason")
            category = _category_from_admission_reason(reason)
            facts.append({
                "category": category,
                "event": "TASK_ADMISSION_DENIED",
                "reason": reason,
                "policy_version": entry.get("policy_version"),
            })

    for entry in executor_entries:
        if entry.get("task_id") != task_id:
            continue
        event = entry.get("event")
        if event == "unknown_prerequisite":
            status = entry.get("status")
            category = "missing_approval" if status == "authority-required" else "unmet_prerequisites"
            facts.append({
                "category": category,
                "event": event,
                "status": status,
                "reason": entry.get("reason"),
                "action_id": entry.get("action_id"),
            })
        if event == "exhaustion":
            facts.append({
                "category": "unmet_prerequisites",
                "event": event,
                "reason": entry.get("reason"),
                "exhaustion_type": entry.get("exhaustion_type"),
            })
        if event == "epr_action" and entry.get("status") == "blocked":
            facts.append({
                "category": "missing_approval",
                "event": event,
                "reason": entry.get("error"),
                "action_id": entry.get("action_id"),
            })
        if entry.get("kind") == "adapter" and entry.get("status") == "failed":
            reason = entry.get("error")
            category = "adapter_unavailability" if _looks_like_adapter_unavailable(reason) else "unmet_prerequisites"
            facts.append({
                "category": category,
                "event": "adapter_step_failed",
                "reason": reason,
            })

    return {
        "view": "explanation",
        "task_id": task_id,
        "facts": facts,
    }


def _explain_routine(routine_id: str) -> dict[str, object]:
    entries = _read_audit_log(Path(ROUTINE_LOG_PATH))
    facts: list[dict[str, object]] = []

    for entry in entries:
        if entry.get("routine_id") != routine_id:
            continue
        event = entry.get("event")
        if event == "routine_evaluation":
            outcome = entry.get("outcome")
            category = "unmet_prerequisites"
            if outcome in {"conflict_paused", "conflict_suppressed"}:
                category = "conflicts"
            facts.append({
                "category": category,
                "event": event,
                "outcome": outcome,
                "details": entry.get("details"),
            })
        if event == "delegated_execution" and entry.get("scope_adherence") is False:
            facts.append({
                "category": "scope_violations",
                "event": event,
                "reason": "scope_adherence_false",
            })
        if event == "routine_conflict_prompt":
            routines_payload = entry.get("routines")
            if isinstance(routines_payload, list):
                for routine in routines_payload:
                    if routine.get("routine_id") == routine_id:
                        facts.append({
                            "category": "conflicts",
                            "event": event,
                            "conflict_id": entry.get("conflict_id"),
                            "why": entry.get("why"),
                        })

    return {
        "view": "explanation",
        "routine_id": routine_id,
        "facts": facts,
    }


def _simulate_task(payload: Mapping[str, object]) -> dict[str, object]:
    task = _parse_task(payload)
    admission_policy = _default_admission_policy()
    ctx = task_admission.AdmissionContext(
        actor="ois",
        mode="simulation",
        node_id="ois",
        vow_digest=None,
        doctrine_digest=None,
        now_utc_iso=None,
    )
    decision = task_admission.admit(task, ctx, admission_policy)
    epr_requirements = _evaluate_epr_requirements(payload.get("epr_actions", ()))

    return {
        "view": "simulation",
        "type": "task",
        "task_id": task.task_id,
        "objective": task.objective,
        "admission": {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "constraints": decision.constraints,
        },
        "execution_plan": [
            {
                "step_id": step.step_id,
                "kind": step.kind,
                "expects": list(step.expects),
            }
            for step in task.steps
        ],
        "required_approvals": epr_requirements,
    }


def _simulate_routine(routine_id: str) -> dict[str, object]:
    registry = RoutineRegistry()
    routine = registry.get_routine(routine_id)
    if routine is None:
        return {
            "view": "simulation",
            "type": "routine",
            "routine_id": routine_id,
            "error": "routine not found",
        }
    return {
        "view": "simulation",
        "type": "routine",
        "routine_id": routine.routine_id,
        "trigger": routine.trigger_description,
        "action": routine.action_description,
        "scope": list(routine.scope),
        "approval": routine.approval.summary,
        "required_approvals": [],
    }


def _simulate_adapter(adapter_id: str, action: str) -> dict[str, object]:
    adapter_cls = list_adapters().get(adapter_id)
    if adapter_cls is None:
        return {
            "view": "simulation",
            "type": "adapter",
            "adapter_id": adapter_id,
            "action": action,
            "error": "adapter not found",
        }
    spec = adapter_cls.action_specs.get(action)
    if spec is None:
        return {
            "view": "simulation",
            "type": "adapter",
            "adapter_id": adapter_id,
            "action": action,
            "error": "action not found",
        }
    required = []
    if spec.requires_privilege:
        required.append(f"privilege:adapter:{adapter_id}:{action}")
    return {
        "view": "simulation",
        "type": "adapter",
        "adapter_id": adapter_id,
        "action": action,
        "authority_impact": spec.authority_impact,
        "external_effects": spec.external_effects,
        "reversibility": spec.reversibility,
        "required_approvals": required,
    }


def _parse_task(payload: Mapping[str, object]) -> task_executor.Task:
    task_id = str(payload.get("task_id", "task-sim"))
    objective = str(payload.get("objective", "simulation"))
    steps_payload = payload.get("steps", [])
    steps: list[task_executor.Step] = []
    if isinstance(steps_payload, list):
        for idx, raw in enumerate(steps_payload):
            if not isinstance(raw, Mapping):
                continue
            step_id = int(raw.get("step_id", idx))
            kind = str(raw.get("kind", "noop"))
            payload_obj = _step_payload(kind, raw.get("payload"))
            expects = raw.get("expects", [])
            expects_list = [str(item) for item in expects] if isinstance(expects, list) else []
            steps.append(task_executor.Step(
                step_id=step_id,
                kind=kind,
                payload=payload_obj,
                expects=tuple(expects_list),
            ))
    return task_executor.Task(
        task_id=task_id,
        objective=objective,
        steps=tuple(steps),
        allow_epr=bool(payload.get("allow_epr", False)),
        required_privileges=tuple(payload.get("required_privileges", ())),
    )


def _step_payload(kind: str, payload: object) -> task_executor.StepPayload:
    if kind == "shell":
        command = ""
        if isinstance(payload, Mapping):
            command = str(payload.get("command", ""))
        return task_executor.ShellPayload(command=command)
    if kind == "python":
        name = "python_callable"
        if isinstance(payload, Mapping):
            name = str(payload.get("name", name))
        return task_executor.PythonPayload(callable=None, name=name)
    if kind == "mesh":
        job = ""
        params: dict[str, object] = {}
        if isinstance(payload, Mapping):
            job = str(payload.get("job", ""))
            params = dict(payload.get("parameters", {}) or {})
        return task_executor.MeshPayload(job=job, parameters=params)
    if kind == "adapter":
        if isinstance(payload, Mapping):
            return task_executor.AdapterPayload(
                adapter_id=str(payload.get("adapter_id", "")),
                action=str(payload.get("action", "")),
                params=dict(payload.get("params", {}) or {}),
                config=dict(payload.get("config", {}) or {}),
            )
        return task_executor.AdapterPayload(adapter_id="", action="", params={}, config={})
    if isinstance(payload, Mapping):
        note = payload.get("note")
        return task_executor.NoopPayload(note=str(note) if note else None)
    return task_executor.NoopPayload()


def _default_admission_policy() -> task_admission.AdmissionPolicy:
    policy_version = os.getenv("SENTIENTOS_ADMISSION_POLICY_VERSION", "default")
    return task_admission.AdmissionPolicy(policy_version=policy_version)


def _evaluate_epr_requirements(raw_actions: object) -> list[dict[str, object]]:
    if not isinstance(raw_actions, list):
        return []
    requirements: list[dict[str, object]] = []
    for action in raw_actions:
        if not isinstance(action, Mapping):
            continue
        authority = str(action.get("authority_impact", "none"))
        reversibility = str(action.get("reversibility", "guaranteed"))
        rollback = str(action.get("rollback_proof", "none"))
        external = str(action.get("external_effects", "no"))
        needs_approval = not (authority == "none" and reversibility == "guaranteed")
        requirement = {
            "action_id": action.get("action_id"),
            "requires_approval": needs_approval,
            "authority_impact": authority,
            "reversibility": reversibility,
            "rollback_proof": rollback,
            "external_effects": external,
        }
        if reversibility == "bounded" and rollback == "none":
            requirement["requires_rollback_proof"] = True
        if external == "yes":
            requirement["violates_external_effects_constraint"] = True
        requirements.append(requirement)
    return requirements


def _category_from_admission_reason(reason: object) -> str:
    if reason in {
        "MISSING_VOW_DIGEST",
        "EXPECTED_VOW_DIGEST_UNSET",
        "VOW_DIGEST_MISMATCH",
        "MISSING_DOCTRINE_DIGEST",
        "EXPECTED_DOCTRINE_DIGEST_UNSET",
        "DOCTRINE_DIGEST_MISMATCH",
    }:
        return "unmet_prerequisites"
    if reason in {
        "DENIED_STEP_KIND",
        "MESH_DISABLED",
        "SHELL_DENIED_IN_AUTONOMOUS",
        "TOO_MANY_STEPS",
        "TOO_MANY_SHELL_STEPS",
        "TOO_MANY_PYTHON_STEPS",
    }:
        return "scope_violations"
    return "unmet_prerequisites"


def _looks_like_adapter_unavailable(reason: object) -> bool:
    if not isinstance(reason, str):
        return False
    lowered = reason.lower()
    return "adapter" in lowered and ("unknown" in lowered or "unavailable" in lowered)


def serialize_output(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)
