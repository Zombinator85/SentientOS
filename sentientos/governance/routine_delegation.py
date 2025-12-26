from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, MutableMapping, Sequence

from logging_config import get_log_path
from log_utils import append_json

RoutineAuthorityImpact = str
RoutineReversibility = str


class RoutinePolicyViolation(RuntimeError):
    """Raised when a routine violates non-negotiable authority bounds."""


class RoutineScopeViolation(RuntimeError):
    """Raised when a routine exceeds its declared scope."""


class RoutineExecutionError(RuntimeError):
    """Raised when a routine cannot execute safely."""


@dataclass(frozen=True)
class RoutineSpec:
    routine_id: str
    trigger_id: str
    trigger_description: str
    action_id: str
    action_description: str
    scope: tuple[str, ...]
    reversibility: RoutineReversibility
    authority_impact: RoutineAuthorityImpact
    expiration: str | None = None
    allows_task_spawn: bool = False
    allows_epr: bool = False
    allows_privilege_escalation: bool = False
    allows_governance_change: bool = False
    allows_config_change: bool = False

    def policy_snapshot(self) -> dict[str, object]:
        return {
            "allows_task_spawn": self.allows_task_spawn,
            "allows_epr": self.allows_epr,
            "allows_privilege_escalation": self.allows_privilege_escalation,
            "allows_governance_change": self.allows_governance_change,
            "allows_config_change": self.allows_config_change,
        }


@dataclass(frozen=True)
class RoutineApproval:
    approval_id: str
    approved_by: str
    approved_at: str
    summary: str
    trigger_summary: str
    scope_summary: tuple[str, ...]
    rationale: str | None = None


@dataclass(frozen=True)
class RoutineDefinition:
    routine_id: str
    trigger_id: str
    trigger_description: str
    action_id: str
    action_description: str
    scope: tuple[str, ...]
    reversibility: RoutineReversibility
    authority_impact: RoutineAuthorityImpact
    expiration: str | None
    approval: RoutineApproval
    created_at: str
    created_by: str
    policy: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "routine_id": self.routine_id,
            "trigger_id": self.trigger_id,
            "trigger_description": self.trigger_description,
            "action_id": self.action_id,
            "action_description": self.action_description,
            "scope": list(self.scope),
            "reversibility": self.reversibility,
            "authority_impact": self.authority_impact,
            "expiration": self.expiration,
            "approval": {
                "approval_id": self.approval.approval_id,
                "approved_by": self.approval.approved_by,
                "approved_at": self.approval.approved_at,
                "summary": self.approval.summary,
                "trigger_summary": self.approval.trigger_summary,
                "scope_summary": list(self.approval.scope_summary),
                "rationale": self.approval.rationale,
            },
            "created_at": self.created_at,
            "created_by": self.created_by,
            "policy": dict(self.policy),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "RoutineDefinition":
        approval_payload = payload.get("approval") or {}
        approval = RoutineApproval(
            approval_id=str(approval_payload.get("approval_id", "")),
            approved_by=str(approval_payload.get("approved_by", "")),
            approved_at=str(approval_payload.get("approved_at", "")),
            summary=str(approval_payload.get("summary", "")),
            trigger_summary=str(approval_payload.get("trigger_summary", "")),
            scope_summary=tuple(str(s) for s in approval_payload.get("scope_summary", ()) if s),
            rationale=approval_payload.get("rationale") if approval_payload.get("rationale") else None,
        )
        return cls(
            routine_id=str(payload.get("routine_id", "")),
            trigger_id=str(payload.get("trigger_id", "")),
            trigger_description=str(payload.get("trigger_description", "")),
            action_id=str(payload.get("action_id", "")),
            action_description=str(payload.get("action_description", "")),
            scope=tuple(str(s) for s in payload.get("scope", ()) if s),
            reversibility=str(payload.get("reversibility", "")),
            authority_impact=str(payload.get("authority_impact", "")),
            expiration=str(payload.get("expiration")) if payload.get("expiration") else None,
            approval=approval,
            created_at=str(payload.get("created_at", "")),
            created_by=str(payload.get("created_by", "")),
            policy=dict(payload.get("policy") or {}),
        )


@dataclass(frozen=True)
class RoutineProposal:
    proposal_id: str
    summary: str
    spec: RoutineSpec
    proposed_by: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "summary": self.summary,
            "spec": _spec_payload(self.spec),
            "proposed_by": self.proposed_by,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RoutineActionResult:
    outcome: str
    details: Mapping[str, object] = field(default_factory=dict)
    affected_scopes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoutineAction:
    action_id: str
    description: str
    handler: Callable[[Mapping[str, object]], RoutineActionResult]


@dataclass(frozen=True)
class RoutineTrigger:
    trigger_id: str
    description: str
    predicate: Callable[[Mapping[str, object]], bool]


@dataclass(frozen=True)
class RoutineExecutionReport:
    routine_id: str
    trigger_evaluation: bool
    action_taken: str | None
    outcome: str
    scope_adherence: bool


DEFAULT_LOG_PATH = get_log_path("routine_delegation.jsonl", "ROUTINE_DELEGATION_LOG")
DEFAULT_STORE_PATH = Path(os.getenv("ROUTINE_DELEGATION_STORE", "config/routine_delegations.json"))


class RoutineCatalog:
    def __init__(self) -> None:
        self._triggers: dict[str, RoutineTrigger] = {}
        self._actions: dict[str, RoutineAction] = {}

    def register_trigger(self, trigger: RoutineTrigger) -> None:
        self._triggers[trigger.trigger_id] = trigger

    def register_action(self, action: RoutineAction) -> None:
        self._actions[action.action_id] = action

    def get_trigger(self, trigger_id: str) -> RoutineTrigger | None:
        return self._triggers.get(trigger_id)

    def get_action(self, action_id: str) -> RoutineAction | None:
        return self._actions.get(action_id)


class RoutineRegistry:
    def __init__(self, *, store_path: Path | None = None, log_path: Path | None = None) -> None:
        self.store_path = store_path or DEFAULT_STORE_PATH
        self.log_path = log_path or DEFAULT_LOG_PATH
        self._state = self._load_state()

    def approve_routine(self, spec: RoutineSpec, approval: RoutineApproval) -> RoutineDefinition:
        self._validate_spec(spec)
        self._validate_approval(spec, approval)
        if spec.routine_id in self._state["routines"]:
            raise RoutinePolicyViolation(f"routine already exists: {spec.routine_id}")
        routine = RoutineDefinition(
            routine_id=spec.routine_id,
            trigger_id=spec.trigger_id,
            trigger_description=spec.trigger_description,
            action_id=spec.action_id,
            action_description=spec.action_description,
            scope=spec.scope,
            reversibility=spec.reversibility,
            authority_impact=spec.authority_impact,
            expiration=spec.expiration,
            approval=approval,
            created_at=approval.approved_at,
            created_by=approval.approved_by,
            policy=spec.policy_snapshot(),
        )
        self._state["routines"][spec.routine_id] = routine.to_dict()
        self._save_state()
        append_json(
            self.log_path,
            {
                "event": "routine_approved",
                "routine_id": routine.routine_id,
                "approval_id": approval.approval_id,
                "approved_by": approval.approved_by,
                "approved_at": approval.approved_at,
                "trigger": routine.trigger_description,
                "action": routine.action_description,
                "scope": routine.scope,
                "authority_impact": routine.authority_impact,
                "reversibility": routine.reversibility,
                "expiration": routine.expiration,
            },
        )
        return routine

    def revoke_routine(self, routine_id: str, *, revoked_by: str, reason: str) -> bool:
        routine_payload = self._state["routines"].pop(routine_id, None)
        if routine_payload is None:
            append_json(
                self.log_path,
                {
                    "event": "routine_revoke_miss",
                    "routine_id": routine_id,
                    "revoked_by": revoked_by,
                    "reason": reason,
                },
            )
            return False
        self._state["revoked"][routine_id] = {
            "revoked_by": revoked_by,
            "revoked_at": _now(),
            "reason": reason,
        }
        self._save_state()
        append_json(
            self.log_path,
            {
                "event": "routine_revoked",
                "routine_id": routine_id,
                "revoked_by": revoked_by,
                "reason": reason,
            },
        )
        return True

    def revoke_all(self, *, revoked_by: str, reason: str) -> tuple[str, ...]:
        routine_ids = tuple(self._state["routines"].keys())
        for routine_id in routine_ids:
            self.revoke_routine(routine_id, revoked_by=revoked_by, reason=reason)
        return routine_ids

    def list_routines(self) -> tuple[RoutineDefinition, ...]:
        return tuple(RoutineDefinition.from_dict(payload) for payload in self._state["routines"].values())

    def get_routine(self, routine_id: str) -> RoutineDefinition | None:
        payload = self._state["routines"].get(routine_id)
        if payload is None:
            return None
        return RoutineDefinition.from_dict(payload)

    def _validate_spec(self, spec: RoutineSpec) -> None:
        if spec.authority_impact not in {"none", "local"}:
            raise RoutinePolicyViolation("routine authority_impact must be none or local")
        if spec.reversibility not in {"guaranteed", "bounded", "none"}:
            raise RoutinePolicyViolation("routine reversibility must be guaranteed, bounded, or none")
        if not spec.scope:
            raise RoutinePolicyViolation("routine scope must be declared")
        if any(flag for flag in spec.policy_snapshot().values()):
            raise RoutinePolicyViolation("routine authority cannot expand beyond declared scope")

    def _validate_approval(self, spec: RoutineSpec, approval: RoutineApproval) -> None:
        if not approval.summary.strip():
            raise RoutinePolicyViolation("approval must include what will happen")
        if not approval.trigger_summary.strip():
            raise RoutinePolicyViolation("approval must include when it will happen")
        if not approval.scope_summary:
            raise RoutinePolicyViolation("approval must include what it can affect")
        if approval.trigger_summary != spec.trigger_description:
            raise RoutinePolicyViolation("approval trigger must match routine definition")
        if tuple(approval.scope_summary) != tuple(spec.scope):
            raise RoutinePolicyViolation("approval scope must match routine definition")

    def _load_state(self) -> MutableMapping[str, MutableMapping[str, object]]:
        if not self.store_path.exists():
            return {"routines": {}, "revoked": {}}
        payload = json.loads(self.store_path.read_text(encoding="utf-8"))
        routines = payload.get("routines", {})
        revoked = payload.get("revoked", {})
        if not isinstance(routines, dict):
            routines = {}
        if not isinstance(revoked, dict):
            revoked = {}
        return {"routines": routines, "revoked": revoked}

    def _save_state(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "routines": self._state["routines"],
            "revoked": self._state["revoked"],
        }
        self.store_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


class RoutineExecutor:
    def __init__(self, *, log_path: Path | None = None) -> None:
        self.log_path = log_path or DEFAULT_LOG_PATH

    def run(
        self,
        routines: Sequence[RoutineDefinition],
        catalog: RoutineCatalog,
        context: Mapping[str, object],
    ) -> tuple[RoutineExecutionReport, ...]:
        reports: list[RoutineExecutionReport] = []
        for routine in routines:
            reports.append(self.execute_routine(routine, catalog, context))
        return tuple(reports)

    def execute_routine(
        self,
        routine: RoutineDefinition,
        catalog: RoutineCatalog,
        context: Mapping[str, object],
    ) -> RoutineExecutionReport:
        if _is_expired(routine.expiration):
            return self._log_evaluation(
                routine,
                triggered=False,
                action_taken=None,
                outcome="expired",
                scope_adherence=True,
            )
        trigger = catalog.get_trigger(routine.trigger_id)
        if trigger is None:
            return self._log_evaluation(
                routine,
                triggered=False,
                action_taken=None,
                outcome="trigger_missing",
                scope_adherence=True,
            )
        triggered = bool(trigger.predicate(context))
        if not triggered:
            return self._log_evaluation(
                routine,
                triggered=False,
                action_taken=None,
                outcome="trigger_not_met",
                scope_adherence=True,
            )
        action = catalog.get_action(routine.action_id)
        if action is None:
            self._log_evaluation(
                routine,
                triggered=True,
                action_taken=None,
                outcome="action_missing",
                scope_adherence=False,
            )
            raise RoutineExecutionError(f"missing routine action: {routine.action_id}")
        result = action.handler(context)
        scope_adherence = _scope_adheres(result.affected_scopes, routine.scope)
        self._log_execution(routine, triggered=True, action_taken=action.action_id, result=result, scope_adherence=scope_adherence)
        if not scope_adherence:
            raise RoutineScopeViolation(f"routine {routine.routine_id} exceeded declared scope")
        return RoutineExecutionReport(
            routine_id=routine.routine_id,
            trigger_evaluation=True,
            action_taken=action.action_id,
            outcome=result.outcome,
            scope_adherence=scope_adherence,
        )

    def _log_evaluation(
        self,
        routine: RoutineDefinition,
        *,
        triggered: bool,
        action_taken: str | None,
        outcome: str,
        scope_adherence: bool,
    ) -> RoutineExecutionReport:
        append_json(
            self.log_path,
            {
                "event": "routine_evaluation",
                "routine_id": routine.routine_id,
                "approval_id": routine.approval.approval_id,
                "trigger_evaluation": triggered,
                "action_taken": action_taken,
                "outcome": outcome,
                "scope_adherence": scope_adherence,
                "scope": routine.scope,
                "authority_impact": routine.authority_impact,
                "reversibility": routine.reversibility,
            },
        )
        return RoutineExecutionReport(
            routine_id=routine.routine_id,
            trigger_evaluation=triggered,
            action_taken=action_taken,
            outcome=outcome,
            scope_adherence=scope_adherence,
        )

    def _log_execution(
        self,
        routine: RoutineDefinition,
        *,
        triggered: bool,
        action_taken: str,
        result: RoutineActionResult,
        scope_adherence: bool,
    ) -> None:
        append_json(
            self.log_path,
            {
                "event": "delegated_execution",
                "routine_id": routine.routine_id,
                "approval_id": routine.approval.approval_id,
                "trigger_evaluation": triggered,
                "action_taken": action_taken,
                "outcome": result.outcome,
                "scope_adherence": scope_adherence,
                "affected_scopes": result.affected_scopes,
                "scope": routine.scope,
                "authority_impact": routine.authority_impact,
                "reversibility": routine.reversibility,
                "details": dict(result.details),
            },
        )


def make_routine_spec(
    *,
    trigger_id: str,
    trigger_description: str,
    action_id: str,
    action_description: str,
    scope: Sequence[str],
    reversibility: RoutineReversibility,
    authority_impact: RoutineAuthorityImpact,
    expiration: str | None = None,
) -> RoutineSpec:
    return RoutineSpec(
        routine_id=f"routine-{uuid.uuid4().hex}",
        trigger_id=trigger_id,
        trigger_description=trigger_description,
        action_id=action_id,
        action_description=action_description,
        scope=tuple(scope),
        reversibility=reversibility,
        authority_impact=authority_impact,
        expiration=expiration,
    )


def make_routine_approval(
    *,
    approved_by: str,
    summary: str,
    trigger_summary: str,
    scope_summary: Sequence[str],
    rationale: str | None = None,
    approved_at: str | None = None,
) -> RoutineApproval:
    return RoutineApproval(
        approval_id=f"approval-{uuid.uuid4().hex}",
        approved_by=approved_by,
        approved_at=approved_at or _now(),
        summary=summary,
        trigger_summary=trigger_summary,
        scope_summary=tuple(scope_summary),
        rationale=rationale,
    )


def make_routine_proposal(*, summary: str, spec: RoutineSpec, proposed_by: str) -> RoutineProposal:
    return RoutineProposal(
        proposal_id=f"proposal-{uuid.uuid4().hex}",
        summary=summary,
        spec=spec,
        proposed_by=proposed_by,
        created_at=_now(),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_expired(expiration: str | None) -> bool:
    if not expiration:
        return False
    try:
        cutoff = datetime.fromisoformat(expiration)
    except ValueError:
        return True
    return datetime.now(timezone.utc) >= cutoff


def _scope_adheres(affected_scopes: Sequence[str], allowed_scopes: Sequence[str]) -> bool:
    if not affected_scopes:
        return True
    return set(affected_scopes).issubset(set(allowed_scopes))


def _spec_payload(spec: RoutineSpec) -> dict[str, object]:
    return {
        "routine_id": spec.routine_id,
        "trigger_id": spec.trigger_id,
        "trigger_description": spec.trigger_description,
        "action_id": spec.action_id,
        "action_description": spec.action_description,
        "scope": list(spec.scope),
        "reversibility": spec.reversibility,
        "authority_impact": spec.authority_impact,
        "expiration": spec.expiration,
        "policy": spec.policy_snapshot(),
    }


__all__ = [
    "RoutineAction",
    "RoutineActionResult",
    "RoutineApproval",
    "RoutineCatalog",
    "RoutineDefinition",
    "RoutineExecutionError",
    "RoutineExecutionReport",
    "RoutinePolicyViolation",
    "RoutineProposal",
    "RoutineRegistry",
    "RoutineScopeViolation",
    "RoutineSpec",
    "RoutineTrigger",
    "make_routine_approval",
    "make_routine_proposal",
    "make_routine_spec",
]
