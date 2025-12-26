from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, MutableMapping, Sequence

from control_plane.records import AuthorizationRecord
from logging_config import get_log_path
from log_utils import append_json

from .base import AdapterActionResult, AdapterRollbackResult, ExecutionContext, ExternalAdapter
from .registry import get_adapter

LOG_PATH = get_log_path("external_adapter_actions.jsonl", "EXTERNAL_ADAPTER_LOG")


class AdapterExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdapterExecutionContext:
    source: str
    task_id: str | None
    routine_id: str | None
    request_fingerprint: str
    authorization: AuthorizationRecord
    admission_token: Mapping[str, object] | None = None
    approved_privileges: Sequence[str] = field(default_factory=tuple)
    required_privileges: Sequence[str] = field(default_factory=tuple)

    def as_log_context(self) -> MutableMapping[str, object]:
        return {
            "source": self.source,
            "task_id": self.task_id,
            "routine_id": self.routine_id,
            "request_fingerprint": self.request_fingerprint,
            "authorization": self.authorization.as_log_entry(),
            "admission_token": dict(self.admission_token) if self.admission_token else None,
            "approved_privileges": list(self.approved_privileges),
            "required_privileges": list(self.required_privileges),
        }


def execute_adapter_action(
    *,
    adapter_id: str,
    action: str,
    params: Mapping[str, object],
    adapter_config: Mapping[str, object] | None = None,
    context: ExecutionContext,
    redact_keys: Iterable[str] = (),
) -> AdapterActionResult:
    adapter_cls = get_adapter(adapter_id)
    adapter = adapter_cls(**(adapter_config or {}))
    _validate_context(adapter, context)
    spec = _require_action(adapter, action)
    _enforce_privileges(adapter_id, action, spec.requires_privilege, context)
    redacted = _redact_params(params, redact_keys)

    try:
        result = adapter.execute(action, params, context)
    except Exception as exc:
        _log_action(
            adapter=adapter,
            action=action,
            spec=spec,
            params=redacted,
            context=context,
            success=False,
            error=str(exc) or exc.__class__.__name__,
            rollback_status=None,
        )
        raise

    _log_action(
        adapter=adapter,
        action=action,
        spec=spec,
        params=redacted,
        context=context,
        success=True,
        error=None,
        rollback_status=None,
    )
    return result


def rollback_adapter_action(
    *,
    adapter_id: str,
    ref: Mapping[str, object],
    adapter_config: Mapping[str, object] | None = None,
    context: ExecutionContext,
    redact_keys: Iterable[str] = (),
) -> AdapterRollbackResult:
    adapter_cls = get_adapter(adapter_id)
    adapter = adapter_cls(**(adapter_config or {}))
    _validate_context(adapter, context)
    action = str(ref.get("action", ""))
    if not action:
        raise AdapterExecutionError("rollback reference missing action")
    spec = _require_action(adapter, action)
    _enforce_privileges(adapter_id, action, spec.requires_privilege, context)

    try:
        result = adapter.rollback(ref, context)
    except Exception as exc:
        _log_action(
            adapter=adapter,
            action=action,
            spec=spec,
            params=_redact_params(ref, redact_keys),
            context=context,
            success=False,
            error=str(exc) or exc.__class__.__name__,
            rollback_status="failed",
        )
        raise

    _log_action(
        adapter=adapter,
        action=action,
        spec=spec,
        params=_redact_params(ref, redact_keys),
        context=context,
        success=result.success,
        error=None if result.success else "rollback_failed",
        rollback_status="completed" if result.success else "failed",
    )
    return result


def _validate_context(adapter: ExternalAdapter, context: ExecutionContext) -> None:
    if context.source not in {"task", "routine", "epr"}:
        raise AdapterExecutionError("adapter execution requires task, routine, or EPR context")
    metadata = adapter.describe()
    if context.source == "epr" and not metadata.allow_epr:
        raise AdapterExecutionError("adapter does not permit EPR invocation")


def _require_action(adapter: ExternalAdapter, action: str):
    spec = adapter.action_specs.get(action)
    if spec is None:
        raise AdapterExecutionError(f"unsupported adapter action: {action}")
    if spec.capability not in adapter.metadata.capabilities:
        raise AdapterExecutionError("adapter action capability not declared")
    return spec


def _enforce_privileges(
    adapter_id: str,
    action: str,
    requires_privilege: bool,
    context: ExecutionContext,
) -> None:
    if not requires_privilege:
        return
    required = set(context.required_privileges)
    if adapter_id not in required and f"{adapter_id}:{action}" not in required:
        raise AdapterExecutionError("adapter privilege not declared in task or routine")
    approved = set(context.approved_privileges)
    if adapter_id not in approved and f"{adapter_id}:{action}" not in approved:
        raise AdapterExecutionError("adapter privilege not approved for execution")


def _redact_params(params: Mapping[str, object], redact_keys: Iterable[str]) -> Mapping[str, object]:
    redacted = dict(params)
    for key in redact_keys:
        if key in redacted:
            redacted[key] = "***"
    return redacted


def _log_action(
    *,
    adapter: ExternalAdapter,
    action: str,
    spec,
    params: Mapping[str, object],
    context: ExecutionContext,
    success: bool,
    error: str | None,
    rollback_status: str | None,
) -> None:
    entry: MutableMapping[str, object] = {
        "event": "adapter_action",
        "adapter_id": adapter.metadata.adapter_id,
        "action": action,
        "capability": spec.capability,
        "parameters": dict(params),
        "authority_impact": spec.authority_impact,
        "external_effects": spec.external_effects,
        "reversibility": spec.reversibility,
        "requires_privilege": spec.requires_privilege,
        "success": success,
        "rollback_status": rollback_status,
        "context": context.as_log_context(),
    }
    if error:
        entry["error"] = error
    append_json(LOG_PATH, entry)


__all__ = [
    "AdapterExecutionContext",
    "AdapterExecutionError",
    "execute_adapter_action",
    "rollback_adapter_action",
]
