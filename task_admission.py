from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import task_executor
from logging_config import get_log_path
from log_utils import append_json
from runtime_mode import IS_LOCAL_OWNER


@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    reason: str
    policy_version: str
    constraints: dict[str, Any]
    redactions: dict[str, Any] | None = None


@dataclass(frozen=True)
class AdmissionContext:
    actor: str
    mode: str
    node_id: str
    vow_digest: str | None
    doctrine_digest: str | None
    now_utc_iso: str | None


@dataclass(frozen=True)
class AdmissionPolicy:
    policy_version: str
    max_steps: int = 64
    max_shell_steps: int = 8
    max_python_steps: int = 16
    allow_mesh: bool = False
    allowed_step_kinds: frozenset[str] | None = field(default=None)
    deny_shell_in_autonomous: bool = True
    require_vow_digest_match: bool = False
    expected_vow_digest: str | None = None
    require_doctrine_digest_match: bool = False
    expected_doctrine_digest: str | None = None

    def __post_init__(self) -> None:
        if self.allowed_step_kinds is None:
            allowed = {"noop", "shell", "python"}
            if self.allow_mesh:
                allowed.add("mesh")
            object.__setattr__(self, "allowed_step_kinds", frozenset(allowed))


ADMISSION_LOG_PATH = get_log_path("task_admission.jsonl", "TASK_ADMISSION_LOG")


def admit(task: task_executor.Task, ctx: AdmissionContext, policy: AdmissionPolicy) -> AdmissionDecision:
    """Deterministically gate tasks without side effects beyond returning a decision."""

    step_count = 0
    shell_count = 0
    python_count = 0
    mesh_count = 0
    denied_kinds: list[str] = []
    redactions: dict[str, Any] = {}
    shell_commands: list[str] = []
    allowed_kinds = policy.allowed_step_kinds or frozenset()

    for step in task.steps:
        step_count += 1
        if step.kind == "shell":
            shell_count += 1
            payload = step.payload
            if isinstance(payload, task_executor.ShellPayload):
                shell_commands.append(payload.command)
        elif step.kind == "python":
            python_count += 1
        elif step.kind == "mesh":
            mesh_count += 1
        if step.kind not in allowed_kinds and step.kind not in denied_kinds:
            denied_kinds.append(step.kind)

    if shell_commands:
        redactions["shell_commands"] = tuple(shell_commands)

    constraints: dict[str, Any] = {
        "step_count": step_count,
        "shell_count": shell_count,
        "python_count": python_count,
        "mesh_count": mesh_count,
        "denied_kinds": tuple(denied_kinds),
    }

    enforce_vow_digest = policy.require_vow_digest_match
    enforce_doctrine_digest = policy.require_doctrine_digest_match
    if IS_LOCAL_OWNER:
        # Owner-controlled local mode: skip semantic/federation constraints
        enforce_vow_digest = False
        enforce_doctrine_digest = False

    if enforce_vow_digest:
        if ctx.vow_digest is None:
            return AdmissionDecision(
                allowed=False,
                reason="MISSING_VOW_DIGEST",
                policy_version=policy.policy_version,
                constraints=constraints,
                redactions=redactions or None,
            )
        if policy.expected_vow_digest is None:
            return AdmissionDecision(
                allowed=False,
                reason="EXPECTED_VOW_DIGEST_UNSET",
                policy_version=policy.policy_version,
                constraints=constraints,
                redactions=redactions or None,
            )
        if ctx.vow_digest != policy.expected_vow_digest:
            return AdmissionDecision(
                allowed=False,
                reason="VOW_DIGEST_MISMATCH",
                policy_version=policy.policy_version,
                constraints=constraints,
                redactions=redactions or None,
            )

    if enforce_doctrine_digest:
        if ctx.doctrine_digest is None:
            return AdmissionDecision(
                allowed=False,
                reason="MISSING_DOCTRINE_DIGEST",
                policy_version=policy.policy_version,
                constraints=constraints,
                redactions=redactions or None,
            )
        if policy.expected_doctrine_digest is None:
            return AdmissionDecision(
                allowed=False,
                reason="EXPECTED_DOCTRINE_DIGEST_UNSET",
                policy_version=policy.policy_version,
                constraints=constraints,
                redactions=redactions or None,
            )
        if ctx.doctrine_digest != policy.expected_doctrine_digest:
            return AdmissionDecision(
                allowed=False,
                reason="DOCTRINE_DIGEST_MISMATCH",
                policy_version=policy.policy_version,
                constraints=constraints,
                redactions=redactions or None,
            )

    if mesh_count > 0 and not policy.allow_mesh:
        return AdmissionDecision(
            allowed=False,
            reason="MESH_DISABLED",
            policy_version=policy.policy_version,
            constraints=constraints,
            redactions=redactions or None,
        )

    if denied_kinds:
        return AdmissionDecision(
            allowed=False,
            reason="DENIED_STEP_KIND",
            policy_version=policy.policy_version,
            constraints=constraints,
            redactions=redactions or None,
        )

    if policy.deny_shell_in_autonomous and ctx.mode == "autonomous" and shell_count:
        return AdmissionDecision(
            allowed=False,
            reason="SHELL_DENIED_IN_AUTONOMOUS",
            policy_version=policy.policy_version,
            constraints=constraints,
            redactions=redactions or None,
        )

    if step_count > policy.max_steps:
        return AdmissionDecision(
            allowed=False,
            reason="TOO_MANY_STEPS",
            policy_version=policy.policy_version,
            constraints=constraints,
            redactions=redactions or None,
        )

    if shell_count > policy.max_shell_steps:
        return AdmissionDecision(
            allowed=False,
            reason="TOO_MANY_SHELL_STEPS",
            policy_version=policy.policy_version,
            constraints=constraints,
            redactions=redactions or None,
        )

    if python_count > policy.max_python_steps:
        return AdmissionDecision(
            allowed=False,
            reason="TOO_MANY_PYTHON_STEPS",
            policy_version=policy.policy_version,
            constraints=constraints,
            redactions=redactions or None,
        )

    return AdmissionDecision(
        allowed=True,
        reason="OK",
        policy_version=policy.policy_version,
        constraints=constraints,
        redactions=redactions or None,
    )


def _log_admission_event(
    decision: AdmissionDecision,
    task: task_executor.Task,
    ctx: AdmissionContext,
    policy: AdmissionPolicy,
    *,
    log_path: Path = ADMISSION_LOG_PATH,
) -> None:
    entry = {
        "event": "TASK_ADMITTED" if decision.allowed else "TASK_ADMISSION_DENIED",
        "task_id": task.task_id,
        "policy_version": policy.policy_version,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "constraints": decision.constraints,
        "actor": ctx.actor,
        "mode": ctx.mode,
        "node_id": ctx.node_id,
        "has_vow_digest": ctx.vow_digest is not None,
        "has_doctrine_digest": ctx.doctrine_digest is not None,
    }
    if ctx.now_utc_iso is not None:
        entry["now_utc_iso"] = ctx.now_utc_iso
    append_json(log_path, entry)


def run_task_with_admission(
    task: task_executor.Task,
    ctx: AdmissionContext,
    policy: AdmissionPolicy,
    executor: Any = task_executor,
) -> tuple[AdmissionDecision, task_executor.TaskResult | None]:
    decision = admit(task, ctx, policy)
    _log_admission_event(decision, task, ctx, policy)
    if not decision.allowed:
        return decision, None
    admission_token = task_executor.AdmissionToken(task_id=task.task_id)
    result = executor.execute_task(task, admission_token=admission_token)
    return decision, result
