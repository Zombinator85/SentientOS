from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping, MutableMapping, Sequence

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
    priority: int | None = None
    precedence_group: str | None = None
    group_priority: int | None = None
    precedence_conditions: tuple[str, ...] = ()
    trigger_specificity: int = 0
    time_window: tuple[str, str] | None = None
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
    priority: int | None
    precedence_group: str | None
    group_priority: int | None
    precedence_conditions: tuple[str, ...]
    trigger_specificity: int
    time_window: tuple[str, str] | None
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
            "priority": self.priority,
            "precedence_group": self.precedence_group,
            "group_priority": self.group_priority,
            "precedence_conditions": list(self.precedence_conditions),
            "trigger_specificity": self.trigger_specificity,
            "time_window": list(self.time_window) if self.time_window else None,
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
            priority=int(payload.get("priority")) if payload.get("priority") is not None else None,
            precedence_group=str(payload.get("precedence_group")) if payload.get("precedence_group") else None,
            group_priority=(
                int(payload.get("group_priority")) if payload.get("group_priority") is not None else None
            ),
            precedence_conditions=tuple(
                str(condition)
                for condition in payload.get("precedence_conditions", ())
                if condition
            ),
            trigger_specificity=int(payload.get("trigger_specificity", 0) or 0),
            time_window=(
                tuple(payload.get("time_window", ()))
                if payload.get("time_window")
                else None
            ),
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
    conflict_domains: tuple[str, ...] = ()
    incompatible_actions: tuple[str, ...] = ()


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


@dataclass(frozen=True)
class _RoutineCandidate:
    routine: RoutineDefinition
    action: RoutineAction


@dataclass(frozen=True)
class _ConflictDecision:
    winner: RoutineDefinition | None
    resolution_path: str | None


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
        if spec.routine_id in self._state["forgotten"]:
            raise RoutinePolicyViolation(f"routine is intentionally forgotten: {spec.routine_id}")
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
            priority=spec.priority,
            precedence_group=spec.precedence_group,
            group_priority=spec.group_priority,
            precedence_conditions=spec.precedence_conditions,
            trigger_specificity=spec.trigger_specificity,
            time_window=spec.time_window,
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

    def forget_routine(self, routine_id: str, *, forgotten_by: str, reason: str) -> bool:
        removed = self._state["routines"].pop(routine_id, None) is not None
        self._state["revoked"].pop(routine_id, None)
        if routine_id in self._state["forgotten"]:
            return removed
        self._state["forgotten"][routine_id] = {
            "forgotten_by": forgotten_by,
            "forgotten_at": _now(),
            "reason": reason,
        }
        self._save_state()
        append_json(
            self.log_path,
            {
                "event": "routine_forgotten",
                "routine_id": routine_id,
                "forgotten_by": forgotten_by,
                "reason": reason,
            },
        )
        return removed

    def forget_all(self, *, forgotten_by: str, reason: str) -> tuple[str, ...]:
        routine_ids = tuple(self._state["routines"].keys())
        for routine_id in routine_ids:
            self.forget_routine(routine_id, forgotten_by=forgotten_by, reason=reason)
        return routine_ids

    def list_routines(self) -> tuple[RoutineDefinition, ...]:
        return tuple(RoutineDefinition.from_dict(payload) for payload in self._state["routines"].values())

    def get_routine(self, routine_id: str) -> RoutineDefinition | None:
        payload = self._state["routines"].get(routine_id)
        if payload is None:
            return None
        return RoutineDefinition.from_dict(payload)

    def list_forgotten(self) -> tuple[str, ...]:
        return tuple(sorted(self._state["forgotten"].keys()))

    def _validate_spec(self, spec: RoutineSpec) -> None:
        if spec.authority_impact not in {"none", "local"}:
            raise RoutinePolicyViolation("routine authority_impact must be none or local")
        if spec.reversibility not in {"guaranteed", "bounded", "none"}:
            raise RoutinePolicyViolation("routine reversibility must be guaranteed, bounded, or none")
        if not spec.scope:
            raise RoutinePolicyViolation("routine scope must be declared")
        if any(flag for flag in spec.policy_snapshot().values()):
            raise RoutinePolicyViolation("routine authority cannot expand beyond declared scope")
        if spec.time_window is not None:
            if len(spec.time_window) != 2:
                raise RoutinePolicyViolation("routine time_window must include start and end times")
            if _parse_time(spec.time_window[0]) is None or _parse_time(spec.time_window[1]) is None:
                raise RoutinePolicyViolation("routine time_window must use HH:MM format")

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
            return {"routines": {}, "revoked": {}, "forgotten": {}}
        payload = json.loads(self.store_path.read_text(encoding="utf-8"))
        routines = payload.get("routines", {})
        revoked = payload.get("revoked", {})
        forgotten = payload.get("forgotten", {})
        if not isinstance(routines, dict):
            routines = {}
        if not isinstance(revoked, dict):
            revoked = {}
        if not isinstance(forgotten, dict):
            forgotten = {}
        return {"routines": routines, "revoked": revoked, "forgotten": forgotten}

    def _save_state(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "routines": self._state["routines"],
            "revoked": self._state["revoked"],
            "forgotten": self._state["forgotten"],
        }
        self.store_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


class RoutineExecutor:
    def __init__(self, *, log_path: Path | None = None) -> None:
        self.log_path = log_path or DEFAULT_LOG_PATH
        self._prompted_conflicts: set[str] = set()

    def run(
        self,
        routines: Sequence[RoutineDefinition],
        catalog: RoutineCatalog,
        context: Mapping[str, object],
    ) -> tuple[RoutineExecutionReport, ...]:
        reports: dict[str, RoutineExecutionReport] = {}
        candidates: list[_RoutineCandidate] = []

        for routine in routines:
            report, candidate = self._evaluate_routine(routine, catalog, context)
            if report is not None:
                reports[routine.routine_id] = report
            if candidate is not None:
                candidates.append(candidate)

        if not candidates:
            return tuple(reports[routine.routine_id] for routine in routines)

        conflict_groups = self._detect_conflicts(candidates)
        suppressed: dict[str, tuple[str, str | None, str | None]] = {}
        paused: dict[str, str] = {}
        winners: dict[str, RoutineDefinition] = {}
        unresolved_conflicts: set[str] = set()

        for group in conflict_groups:
            decision = self._resolve_conflict(group, context)
            conflict_id = self._conflict_id(group)
            conflict_domains = self._conflict_domains(group)
            self._log_conflict_detected(group, conflict_id, conflict_domains)
            if decision.winner is None:
                self._log_conflict_prompt(group, conflict_id, conflict_domains)
                unresolved_conflicts.add(conflict_id)
                for candidate in group:
                    paused[candidate.routine.routine_id] = conflict_id
                continue
            winners[decision.winner.routine_id] = decision.winner
            suppressed_ids = [
                candidate.routine.routine_id
                for candidate in group
                if candidate.routine.routine_id != decision.winner.routine_id
            ]
            self._log_conflict_resolution(
                conflict_id,
                decision.winner,
                suppressed_ids,
                decision.resolution_path,
            )
            for candidate in group:
                if candidate.routine.routine_id == decision.winner.routine_id:
                    continue
                suppressed[candidate.routine.routine_id] = (
                    conflict_id,
                    decision.resolution_path,
                    decision.winner.routine_id,
                )

        if unresolved_conflicts:
            self._prompted_conflicts.intersection_update(unresolved_conflicts)
        else:
            self._prompted_conflicts.clear()

        for candidate in candidates:
            routine_id = candidate.routine.routine_id
            if routine_id in reports:
                continue
            if routine_id in paused:
                reports[routine_id] = self._log_evaluation(
                    candidate.routine,
                    triggered=True,
                    action_taken=None,
                    outcome="conflict_paused",
                    scope_adherence=True,
                    details={"conflict_id": paused[routine_id]},
                )
                continue
            if routine_id in suppressed:
                conflict_id, resolution_path, winner_id = suppressed[routine_id]
                reports[routine_id] = self._log_evaluation(
                    candidate.routine,
                    triggered=True,
                    action_taken=None,
                    outcome="conflict_suppressed",
                    scope_adherence=True,
                    details={
                        "conflict_id": conflict_id,
                        "resolution_path": resolution_path,
                        "winner_routine_id": winner_id,
                    },
                )
                continue
            if routine_id in winners or routine_id not in suppressed:
                reports[routine_id] = self._execute_triggered_routine(candidate, context)

        return tuple(reports[routine.routine_id] for routine in routines)

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

    def _evaluate_routine(
        self,
        routine: RoutineDefinition,
        catalog: RoutineCatalog,
        context: Mapping[str, object],
    ) -> tuple[RoutineExecutionReport | None, _RoutineCandidate | None]:
        if _is_expired(routine.expiration):
            return (
                self._log_evaluation(
                    routine,
                    triggered=False,
                    action_taken=None,
                    outcome="expired",
                    scope_adherence=True,
                ),
                None,
            )
        trigger = catalog.get_trigger(routine.trigger_id)
        if trigger is None:
            return (
                self._log_evaluation(
                    routine,
                    triggered=False,
                    action_taken=None,
                    outcome="trigger_missing",
                    scope_adherence=True,
                ),
                None,
            )
        triggered = bool(trigger.predicate(context))
        if not triggered:
            return (
                self._log_evaluation(
                    routine,
                    triggered=False,
                    action_taken=None,
                    outcome="trigger_not_met",
                    scope_adherence=True,
                ),
                None,
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
        return None, _RoutineCandidate(routine=routine, action=action)

    def _detect_conflicts(
        self,
        candidates: Sequence[_RoutineCandidate],
    ) -> list[tuple[_RoutineCandidate, ...]]:
        if len(candidates) < 2:
            return []
        adjacency: dict[str, set[str]] = {candidate.routine.routine_id: set() for candidate in candidates}
        candidate_map = {candidate.routine.routine_id: candidate for candidate in candidates}
        for left in candidates:
            for right in candidates:
                if left.routine.routine_id >= right.routine.routine_id:
                    continue
                if not _scopes_overlap(left.routine.scope, right.routine.scope):
                    continue
                if not _actions_incompatible(left, right):
                    continue
                adjacency[left.routine.routine_id].add(right.routine.routine_id)
                adjacency[right.routine.routine_id].add(left.routine.routine_id)

        visited: set[str] = set()
        groups: list[tuple[_RoutineCandidate, ...]] = []
        for routine_id in adjacency:
            if routine_id in visited:
                continue
            stack = [routine_id]
            component: set[str] = set()
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                component.add(current)
                stack.extend(adjacency[current] - visited)
            if len(component) > 1:
                groups.append(tuple(candidate_map[rid] for rid in sorted(component)))
        return groups

    def _resolve_conflict(
        self,
        group: Sequence[_RoutineCandidate],
        context: Mapping[str, object],
    ) -> _ConflictDecision:
        explicit_winner = self._resolve_by_explicit_precedence(group, context)
        if explicit_winner is not None:
            return _ConflictDecision(winner=explicit_winner, resolution_path="operator_precedence")
        specific_winner = self._resolve_by_specificity(group)
        if specific_winner is not None:
            return _ConflictDecision(winner=specific_winner, resolution_path="contextual_specialization")
        temporal_winner = self._resolve_by_temporal_specificity(group, context)
        if temporal_winner is not None:
            return _ConflictDecision(winner=temporal_winner, resolution_path="temporal_specificity")
        return _ConflictDecision(winner=None, resolution_path=None)

    def _resolve_by_explicit_precedence(
        self,
        group: Sequence[_RoutineCandidate],
        context: Mapping[str, object],
    ) -> RoutineDefinition | None:
        scored: list[tuple[int, str, RoutineDefinition]] = []
        for candidate in group:
            routine = candidate.routine
            if routine.precedence_conditions and not _conditions_met(routine.precedence_conditions, context):
                continue
            if routine.priority is not None:
                scored.append((routine.priority, "priority", routine))
            if routine.group_priority is not None:
                scored.append((routine.group_priority, "group", routine))
        if not scored:
            return None
        scored.sort(key=lambda item: (-item[0], item[1], item[2].routine_id))
        top_score = scored[0][0]
        top_routines = {routine.routine_id for score, _, routine in scored if score == top_score}
        if len(top_routines) != 1:
            return None
        return scored[0][2]

    def _resolve_by_specificity(self, group: Sequence[_RoutineCandidate]) -> RoutineDefinition | None:
        specifics = sorted(
            (
                (candidate.routine.trigger_specificity, candidate.routine.routine_id, candidate.routine)
                for candidate in group
            ),
            key=lambda entry: (-entry[0], entry[1]),
        )
        if not specifics:
            return None
        top_specificity = specifics[0][0]
        if sum(1 for entry in specifics if entry[0] == top_specificity) != 1:
            return None
        return specifics[0][2]

    def _resolve_by_temporal_specificity(
        self,
        group: Sequence[_RoutineCandidate],
        context: Mapping[str, object],
    ) -> RoutineDefinition | None:
        time_bound: list[RoutineDefinition] = []
        for candidate in group:
            routine = candidate.routine
            if routine.time_window and _time_in_window(routine.time_window, context.get("time")):
                time_bound.append(routine)
        if len(time_bound) == 1:
            return time_bound[0]
        return None

    def _conflict_domains(self, group: Sequence[_RoutineCandidate]) -> tuple[str, ...]:
        domains: set[str] = set()
        for candidate in group:
            action_domains = candidate.action.conflict_domains
            if action_domains:
                domains.update(action_domains)
            else:
                domains.update(candidate.routine.scope)
        return tuple(sorted(domains))

    def _conflict_id(self, group: Sequence[_RoutineCandidate]) -> str:
        routine_ids = sorted(candidate.routine.routine_id for candidate in group)
        domains = self._conflict_domains(group)
        key = "|".join(routine_ids) + "::" + "|".join(domains)
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]

    def _log_conflict_detected(
        self,
        group: Sequence[_RoutineCandidate],
        conflict_id: str,
        conflict_domains: Sequence[str],
    ) -> None:
        append_json(
            self.log_path,
            {
                "event": "routine_conflict_detected",
                "conflict_id": conflict_id,
                "routine_ids": [candidate.routine.routine_id for candidate in group],
                "triggers": [candidate.routine.trigger_description for candidate in group],
                "actions": [candidate.routine.action_description for candidate in group],
                "scopes": [candidate.routine.scope for candidate in group],
                "conflict_domains": list(conflict_domains),
                "reason": "overlapping_scope_incompatible_actions",
            },
        )

    def _log_conflict_resolution(
        self,
        conflict_id: str,
        winner: RoutineDefinition,
        suppressed: Sequence[str],
        resolution_path: str | None,
    ) -> None:
        append_json(
            self.log_path,
            {
                "event": "routine_conflict_resolved",
                "conflict_id": conflict_id,
                "winner_routine_id": winner.routine_id,
                "suppressed_routine_ids": list(suppressed),
                "resolution_path": resolution_path or "unknown",
                "status": "resolved",
            },
        )

    def _log_conflict_prompt(
        self,
        group: Sequence[_RoutineCandidate],
        conflict_id: str,
        conflict_domains: Sequence[str],
    ) -> None:
        if conflict_id in self._prompted_conflicts:
            return
        self._prompted_conflicts.add(conflict_id)
        append_json(
            self.log_path,
            {
                "event": "routine_conflict_prompt",
                "conflict_id": conflict_id,
                "status": "needs_operator_input",
                "conflict_domains": list(conflict_domains),
                "routines": [
                    {
                        "routine_id": candidate.routine.routine_id,
                        "trigger": candidate.routine.trigger_description,
                        "action": candidate.routine.action_description,
                    }
                    for candidate in group
                ],
                "why": "no_deterministic_precedence",
                "options": [
                    "choose_precedence",
                    "restrict_scope",
                    "disable_routine",
                    "allow_both_with_conditions",
                ],
            },
        )

    def _execute_triggered_routine(
        self,
        candidate: _RoutineCandidate,
        context: Mapping[str, object],
    ) -> RoutineExecutionReport:
        result = candidate.action.handler(context)
        scope_adherence = _scope_adheres(result.affected_scopes, candidate.routine.scope)
        self._log_execution(
            candidate.routine,
            triggered=True,
            action_taken=candidate.action.action_id,
            result=result,
            scope_adherence=scope_adherence,
        )
        if not scope_adherence:
            raise RoutineScopeViolation(f"routine {candidate.routine.routine_id} exceeded declared scope")
        return RoutineExecutionReport(
            routine_id=candidate.routine.routine_id,
            trigger_evaluation=True,
            action_taken=candidate.action.action_id,
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
        details: Mapping[str, object] | None = None,
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
                "details": dict(details or {}),
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
    priority: int | None = None,
    precedence_group: str | None = None,
    group_priority: int | None = None,
    precedence_conditions: Sequence[str] = (),
    trigger_specificity: int = 0,
    time_window: tuple[str, str] | None = None,
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
        priority=priority,
        precedence_group=precedence_group,
        group_priority=group_priority,
        precedence_conditions=tuple(precedence_conditions),
        trigger_specificity=trigger_specificity,
        time_window=time_window,
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


def _scopes_overlap(left: Sequence[str], right: Sequence[str]) -> bool:
    return bool(set(left).intersection(set(right)))


def _actions_incompatible(left: _RoutineCandidate, right: _RoutineCandidate) -> bool:
    if left.action.action_id == right.action.action_id:
        return False
    if right.action.action_id in left.action.incompatible_actions:
        return True
    if left.action.action_id in right.action.incompatible_actions:
        return True
    left_domains = set(left.action.conflict_domains or left.routine.scope)
    right_domains = set(right.action.conflict_domains or right.routine.scope)
    return bool(left_domains.intersection(right_domains))


def _conditions_met(conditions: Iterable[str], context: Mapping[str, object]) -> bool:
    if not conditions:
        return True
    return all(bool(context.get(condition)) for condition in conditions)


def _time_in_window(window: tuple[str, str], context_time: object) -> bool:
    if not isinstance(context_time, str):
        return False
    if len(window) != 2:
        return False
    start = _parse_time(window[0])
    end = _parse_time(window[1])
    current = _parse_time(context_time)
    if start is None or end is None or current is None:
        return False
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def _parse_time(value: str) -> time | None:
    try:
        hours, minutes = value.split(":")
        return time(hour=int(hours), minute=int(minutes))
    except ValueError:
        return None


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
        "priority": spec.priority,
        "precedence_group": spec.precedence_group,
        "group_priority": spec.group_priority,
        "precedence_conditions": list(spec.precedence_conditions),
        "trigger_specificity": spec.trigger_specificity,
        "time_window": list(spec.time_window) if spec.time_window else None,
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
