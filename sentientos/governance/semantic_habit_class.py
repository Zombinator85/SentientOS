from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping

from logging_config import get_log_path
from log_utils import append_json
from sentientos.governance.routine_delegation import RoutineDefinition, RoutineRegistry


DEFAULT_LOG_PATH = get_log_path(
    "semantic_habit_classes.jsonl",
    "SEMANTIC_HABIT_CLASS_LOG",
)


@dataclass(frozen=True)
class SemanticHabitClassProposal:
    proposal_id: str
    name: str
    summary: str
    routine_ids: tuple[str, ...]
    scope: tuple[str, ...]
    rationale: str
    proposed_by: str
    proposed_at: str
    signature: str


@dataclass(frozen=True)
class SemanticHabitClass:
    class_id: str
    name: str
    description: str
    routine_ids: tuple[str, ...]
    scope: tuple[str, ...]
    created_by: str
    created_at: str
    revoked_at: str | None = None
    revoked_by: str | None = None
    revoke_reason: str | None = None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


@dataclass
class SemanticHabitClassManager:
    registry: RoutineRegistry
    log_path: str = field(default_factory=lambda: str(DEFAULT_LOG_PATH))
    _classes: MutableMapping[str, SemanticHabitClass] = field(default_factory=dict)
    _proposals: MutableMapping[str, SemanticHabitClassProposal] = field(default_factory=dict)
    _declined_signatures: MutableMapping[str, str] = field(default_factory=dict)
    _forgotten_classes: MutableMapping[str, str] = field(default_factory=dict)

    def propose_class(
        self,
        name: str,
        *,
        routine_ids: Iterable[str],
        proposed_by: str,
        rationale: str,
        proposed_at: str | None = None,
    ) -> SemanticHabitClassProposal | None:
        if name in self._forgotten_classes:
            return None
        routine_ids_tuple = tuple(sorted(set(routine_ids)))
        if len(routine_ids_tuple) < 2:
            raise ValueError("semantic habit classes require at least two routines")
        routines = self._resolve_routines(routine_ids_tuple)
        scope = _scope_union(routines)
        signature = _proposal_signature(name, routine_ids_tuple, rationale)
        if signature in self._declined_signatures:
            return None
        proposal_id = f"shc-{signature[:12]}"
        proposal = SemanticHabitClassProposal(
            proposal_id=proposal_id,
            name=name,
            summary=_proposal_summary(name, routine_ids_tuple, rationale),
            routine_ids=routine_ids_tuple,
            scope=scope,
            rationale=rationale,
            proposed_by=proposed_by,
            proposed_at=proposed_at or _now(),
            signature=signature,
        )
        self._proposals[proposal_id] = proposal
        self._log_event(
            "semantic_class_proposed",
            {
                "proposal_id": proposal_id,
                "name": name,
                "routine_ids": routine_ids_tuple,
                "scope": list(scope),
                "rationale": rationale,
                "proposed_by": proposed_by,
                "proposed_at": proposal.proposed_at,
                "summary": proposal.summary,
                "semantic_only": True,
                "authority_impact": "none",
            },
        )
        return proposal

    def approve_proposal(
        self,
        proposal_id: str,
        *,
        approved_by: str,
        description: str,
        approved_at: str | None = None,
    ) -> SemanticHabitClass:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise ValueError(f"Unknown semantic habit class proposal: {proposal_id}")
        if proposal.name in self._forgotten_classes:
            raise ValueError(f"Semantic habit class is intentionally forgotten: {proposal.name}")
        if proposal.name in self._classes:
            raise ValueError(f"Semantic habit class already exists: {proposal.name}")
        routine_ids = proposal.routine_ids
        routines = self._resolve_routines(routine_ids)
        scope = _scope_union(routines)
        semantic_class = SemanticHabitClass(
            class_id=f"class-{proposal.signature[:16]}",
            name=proposal.name,
            description=description,
            routine_ids=routine_ids,
            scope=scope,
            created_by=approved_by,
            created_at=approved_at or _now(),
        )
        self._classes[proposal.name] = semantic_class
        self._proposals.pop(proposal_id, None)
        self._log_event(
            "semantic_class_approved",
            {
                "proposal_id": proposal_id,
                "class_id": semantic_class.class_id,
                "name": semantic_class.name,
                "routine_ids": routine_ids,
                "scope": list(scope),
                "approved_by": approved_by,
                "approved_at": semantic_class.created_at,
                "semantic_only": True,
                "authority_impact": "none",
            },
        )
        return semantic_class

    def decline_proposal(self, proposal_id: str, *, declined_by: str, reason: str) -> None:
        proposal = self._proposals.pop(proposal_id, None)
        if proposal is None:
            return
        self._declined_signatures[proposal.signature] = reason
        self._log_event(
            "semantic_class_declined",
            {
                "proposal_id": proposal_id,
                "name": proposal.name,
                "routine_ids": proposal.routine_ids,
                "declined_by": declined_by,
                "reason": reason,
                "semantic_only": True,
                "authority_impact": "none",
            },
        )

    def create_class(
        self,
        name: str,
        *,
        routine_ids: Iterable[str],
        created_by: str,
        description: str,
        created_at: str | None = None,
    ) -> SemanticHabitClass:
        if name in self._forgotten_classes:
            raise ValueError(f"Semantic habit class is intentionally forgotten: {name}")
        if name in self._classes:
            raise ValueError(f"Semantic habit class already exists: {name}")
        routine_ids_tuple = tuple(sorted(set(routine_ids)))
        if not routine_ids_tuple:
            raise ValueError("semantic habit classes require at least one routine")
        routines = self._resolve_routines(routine_ids_tuple)
        scope = _scope_union(routines)
        semantic_class = SemanticHabitClass(
            class_id=f"class-{_digest_name(name)}",
            name=name,
            description=description,
            routine_ids=routine_ids_tuple,
            scope=scope,
            created_by=created_by,
            created_at=created_at or _now(),
        )
        self._classes[name] = semantic_class
        self._log_event(
            "semantic_class_created",
            {
                "class_id": semantic_class.class_id,
                "name": semantic_class.name,
                "routine_ids": routine_ids_tuple,
                "scope": list(scope),
                "created_by": created_by,
                "created_at": semantic_class.created_at,
                "semantic_only": True,
                "authority_impact": "none",
            },
        )
        return semantic_class

    def add_member(
        self,
        name: str,
        *,
        routine_id: str,
        approved_by: str,
        approved_at: str | None = None,
    ) -> SemanticHabitClass:
        semantic_class = self._require_class(name)
        if not semantic_class.is_active:
            raise ValueError(f"Semantic habit class is revoked: {name}")
        routines = self._resolve_routines((routine_id,))
        if routine_id in semantic_class.routine_ids:
            return semantic_class
        updated_routines = tuple(sorted((*semantic_class.routine_ids, routine_id)))
        scope = _scope_union((*self._resolve_routines(semantic_class.routine_ids), *routines))
        semantic_class = semantic_class.__class__(
            **{**semantic_class.__dict__, "routine_ids": updated_routines, "scope": scope}
        )
        self._classes[name] = semantic_class
        self._log_event(
            "semantic_class_member_added",
            {
                "class_id": semantic_class.class_id,
                "name": semantic_class.name,
                "routine_id": routine_id,
                "scope": list(scope),
                "approved_by": approved_by,
                "approved_at": approved_at or _now(),
                "semantic_only": True,
                "authority_impact": "none",
            },
        )
        return semantic_class

    def remove_member(
        self,
        name: str,
        *,
        routine_id: str,
        removed_by: str,
        reason: str,
    ) -> SemanticHabitClass:
        semantic_class = self._require_class(name)
        if routine_id not in semantic_class.routine_ids:
            return semantic_class
        updated_routines = tuple(rid for rid in semantic_class.routine_ids if rid != routine_id)
        scope = _scope_union(self._resolve_routines(updated_routines)) if updated_routines else ()
        semantic_class = semantic_class.__class__(
            **{**semantic_class.__dict__, "routine_ids": updated_routines, "scope": scope}
        )
        self._classes[name] = semantic_class
        self._log_event(
            "semantic_class_member_removed",
            {
                "class_id": semantic_class.class_id,
                "name": semantic_class.name,
                "routine_id": routine_id,
                "scope": list(scope),
                "removed_by": removed_by,
                "reason": reason,
                "semantic_only": True,
                "authority_impact": "none",
            },
        )
        return semantic_class

    def revoke_class(self, name: str, *, revoked_by: str, reason: str) -> SemanticHabitClass:
        semantic_class = self._require_class(name)
        if not semantic_class.is_active:
            return semantic_class
        updated = semantic_class.__class__(
            **{
                **semantic_class.__dict__,
                "revoked_at": _now(),
                "revoked_by": revoked_by,
                "revoke_reason": reason,
            }
        )
        self._classes[name] = updated
        self._log_event(
            "semantic_class_revoked",
            {
                "class_id": updated.class_id,
                "name": updated.name,
                "routine_ids": updated.routine_ids,
                "revoked_by": revoked_by,
                "revoked_at": updated.revoked_at,
                "reason": reason,
                "semantic_only": True,
                "authority_impact": "none",
            },
        )
        return updated

    def forget_class(self, name: str, *, forgotten_by: str, reason: str) -> SemanticHabitClass | None:
        semantic_class = self._classes.pop(name, None)
        if semantic_class is None:
            self._proposals = {
                key: proposal for key, proposal in self._proposals.items() if proposal.name != name
            }
            self._forgotten_classes.setdefault(name, reason)
            return None
        self._forgotten_classes[name] = reason
        self._proposals = {
            key: proposal for key, proposal in self._proposals.items() if proposal.name != name
        }
        self._log_event(
            "semantic_class_forgotten",
            {
                "class_id": semantic_class.class_id,
                "name": semantic_class.name,
                "forgotten_by": forgotten_by,
                "reason": reason,
                "semantic_only": True,
                "authority_impact": "none",
            },
        )
        return semantic_class

    def get_class(self, name: str) -> SemanticHabitClass | None:
        return self._classes.get(name)

    def get_class_by_id(self, class_id: str) -> SemanticHabitClass | None:
        for semantic_class in self._classes.values():
            if semantic_class.class_id == class_id:
                return semantic_class
        return None

    def list_classes(self) -> tuple[SemanticHabitClass, ...]:
        return tuple(self._classes.values())

    def list_proposals(self) -> tuple[SemanticHabitClassProposal, ...]:
        return tuple(self._proposals.values())

    def list_forgotten(self) -> tuple[str, ...]:
        return tuple(sorted(self._forgotten_classes.keys()))

    def _resolve_routines(self, routine_ids: Iterable[str]) -> tuple[RoutineDefinition, ...]:
        routines = []
        for routine_id in routine_ids:
            routine = self.registry.get_routine(routine_id)
            if routine is None:
                raise ValueError(f"Unknown routine: {routine_id}")
            routines.append(routine)
        return tuple(routines)

    def _require_class(self, name: str) -> SemanticHabitClass:
        semantic_class = self._classes.get(name)
        if semantic_class is None:
            raise ValueError(f"Unknown semantic habit class: {name}")
        return semantic_class

    def _log_event(self, event: str, payload: Mapping[str, object]) -> None:
        append_json(
            Path(self.log_path),
            {
                "timestamp": _now(),
                "event": event,
                "payload": dict(payload),
            },
        )


def _scope_union(routines: Iterable[RoutineDefinition]) -> tuple[str, ...]:
    scopes = []
    seen = set()
    for routine in routines:
        for scope in routine.scope:
            if scope not in seen:
                seen.add(scope)
                scopes.append(scope)
    return tuple(scopes)


def _proposal_signature(name: str, routine_ids: tuple[str, ...], rationale: str) -> str:
    payload = {
        "name": name,
        "routine_ids": list(routine_ids),
        "rationale": rationale,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _proposal_summary(name: str, routine_ids: tuple[str, ...], rationale: str) -> str:
    routines = ", ".join(routine_ids)
    return (
        f"Create semantic habit class '{name}' for routines [{routines}]. "
        f"Shared semantics: {rationale}. This does not create new behavior."
    )


def _digest_name(name: str) -> str:
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "SemanticHabitClass",
    "SemanticHabitClassManager",
    "SemanticHabitClassProposal",
]
