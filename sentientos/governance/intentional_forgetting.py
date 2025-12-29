from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping, Protocol, Sequence

from logging_config import get_log_path
from log_utils import append_json, read_json
from sentientos.cognition.surface import CognitiveSurface
from sentientos.cor import CORSubsystem
from sentientos.governance.habit_inference import HabitInferenceEngine
from sentientos.governance.routine_delegation import RoutineRegistry
from sentientos.governance.semantic_habit_class import SemanticHabitClass, SemanticHabitClassManager
from sentientos.introspection.spine import EventType, emit_introspection_event
from sentientos.ssu import SymbolicScreenUnderstanding


DEFAULT_LOG_PATH = get_log_path("intentional_forgetting.jsonl", "INTENTIONAL_FORGET_LOG")


@dataclass(frozen=True)
class IntentionalForgetRequest:
    target_type: str
    target_id: str
    forget_scope: str
    proof_level: str
    defer_acknowledged: bool = False


@dataclass(frozen=True)
class IntentionalForgetResult:
    target_type: str
    target_id: str
    forget_scope: str
    proof_level: str
    timestamp: str
    forget_tx_id: str
    replayed: bool
    cascade: bool
    post_state_hash: str
    impacted: tuple[str, ...] = ()
    redacted_target: bool = False


class ForgetCommitPhase(str, Enum):
    PREPARED = "prepared"
    APPLYING = "applying"
    COMMITTED = "committed"
    ABORTED = "aborted"


class ForgetBoundaryDecision(str, Enum):
    ALLOW = "allow"
    REFUSE = "refuse"
    DEFER = "defer"


@dataclass(frozen=True)
class ForgetBoundaryPreview:
    subsystem: str
    decision: ForgetBoundaryDecision
    reason: str


@dataclass(frozen=True)
class ForgetBoundaryVerification:
    subsystem: str
    status: str
    reason: str


@dataclass(frozen=True)
class ForgetPressureSignal:
    forget_tx_id: str
    target_type: str
    target: str
    forget_scope: str
    proof_level: str
    authority: str
    status: str
    phase: str
    subsystems: tuple[dict[str, str], ...]
    redacted_target: bool = False
    defer_acknowledged: bool = False


@dataclass(frozen=True)
class ForgetPressureBudget:
    max_outstanding: int | None = None
    max_duration: int | None = None
    max_weight: float | None = None
    advisory: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "max_outstanding": self.max_outstanding,
            "max_duration": self.max_duration,
            "max_weight": self.max_weight,
            "advisory": self.advisory,
        }


DEFAULT_PRESSURE_BUDGETS: tuple[tuple[str, ForgetPressureBudget], ...] = (
    ("default", ForgetPressureBudget(max_outstanding=25, max_duration=500, max_weight=25.0)),
)


class ForgetBoundaryContract(Protocol):
    name: str

    def preview_forget(self, request: IntentionalForgetRequest) -> ForgetBoundaryPreview | None:
        ...

    def verify_post_commit(self, state: Mapping[str, object]) -> ForgetBoundaryVerification | None:
        ...


@dataclass(frozen=True)
class ForgetDiff:
    request: Mapping[str, str]
    forget_tx_id: str
    replay_status: str
    phase: str | None
    execution_status: str
    primary_targets: tuple[str, ...]
    cascaded_removals: tuple[str, ...]
    removals: tuple[str, ...]
    authority_deltas: tuple[dict[str, object], ...]
    blocked: tuple[dict[str, str], ...]
    skipped: tuple[dict[str, str], ...]
    narrative_summary_hashes: tuple[dict[str, str], ...]
    state_hashes: Mapping[str, str]
    invariant_status: str
    invariant_violations: tuple[dict[str, str], ...]
    boundary_previews: tuple[dict[str, object], ...]
    pressure: tuple[dict[str, object], ...]
    pressure_budgets: tuple[dict[str, object], ...]
    diff_hash: str

    def to_dict(self) -> dict[str, object]:
        return {
            "view": "intentional_forget_diff",
            "request": dict(self.request),
            "forget_tx_id": self.forget_tx_id,
            "replay_status": self.replay_status,
            "phase": self.phase,
            "execution_status": self.execution_status,
            "primary_targets": list(self.primary_targets),
            "cascaded_removals": list(self.cascaded_removals),
            "removals": list(self.removals),
            "authority_deltas": [dict(item) for item in self.authority_deltas],
            "blocked": [dict(item) for item in self.blocked],
            "skipped": [dict(item) for item in self.skipped],
            "narrative_summary_hashes": [dict(item) for item in self.narrative_summary_hashes],
            "state_hashes": dict(self.state_hashes),
            "invariant_status": self.invariant_status,
            "invariant_violations": [dict(item) for item in self.invariant_violations],
            "boundary_previews": [dict(item) for item in self.boundary_previews],
            "pressure": [dict(item) for item in self.pressure],
            "pressure_budgets": [dict(item) for item in self.pressure_budgets],
            "diff_hash": self.diff_hash,
        }


@dataclass
class _ForgetOutcome:
    primary: list[str] = field(default_factory=list)
    cascaded: list[str] = field(default_factory=list)
    removals: list[str] = field(default_factory=list)
    blocked: list[dict[str, str]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class _ForgetPhaseState:
    phase: str | None
    execution_status: str


class _SilentHabitInferenceEngine(HabitInferenceEngine):
    def _log_event(self, kind: str, payload: Mapping[str, object]) -> None:
        return None


class _SilentCORSubsystem(CORSubsystem):
    def _log_event(self, kind: str, payload: dict[str, object]) -> None:
        return None


class InvariantViolation(RuntimeError):
    def __init__(self, violations: Sequence[Mapping[str, str]]) -> None:
        self.violations = tuple(dict(item) for item in violations)
        message = "Post-commit invariant violation: " + ", ".join(
            f"{item.get('reason')}" for item in self.violations
        )
        super().__init__(message)


class BoundaryRefusal(RuntimeError):
    def __init__(self, blockers: Sequence[Mapping[str, str]]) -> None:
        self.blockers = tuple(dict(item) for item in blockers)
        message = "Boundary refusal: " + ", ".join(
            f"{item.get('target')}" for item in self.blockers
        )
        super().__init__(message)


@dataclass
class IntentionalForgettingService:
    routine_registry: RoutineRegistry = field(default_factory=RoutineRegistry)
    habit_engine: HabitInferenceEngine | None = None
    class_manager: SemanticHabitClassManager | None = None
    cor_subsystem: CORSubsystem | None = None
    ssu: SymbolicScreenUnderstanding | None = None
    cognitive_surface: CognitiveSurface | None = None
    log_path: Path = field(default_factory=lambda: Path(DEFAULT_LOG_PATH))
    boundary_contracts: tuple[ForgetBoundaryContract, ...] = ()
    pressure_budgets: Mapping[str, ForgetPressureBudget] = field(
        default_factory=lambda: dict(DEFAULT_PRESSURE_BUDGETS)
    )

    def forget(
        self,
        request: IntentionalForgetRequest,
        *,
        authority: str = "operator",
    ) -> IntentionalForgetResult:
        from sentientos.authority_surface import build_authority_surface_snapshot_for_state

        timestamp = _now()
        cascade = request.forget_scope == "cascade"
        forget_tx_id = self._forget_tx_id(request, authority=authority)
        self._recover_incomplete_transactions()
        prior_entry = _find_forget_tx_entry(read_forget_log(self.log_path), forget_tx_id)
        if prior_entry is not None:
            return IntentionalForgetResult(
                target_type=request.target_type,
                target_id=request.target_id,
                forget_scope=request.forget_scope,
                proof_level=request.proof_level,
                timestamp=timestamp,
                forget_tx_id=forget_tx_id,
                replayed=True,
                cascade=cascade,
                post_state_hash=str(prior_entry.get("post_state_hash", "")),
                impacted=(),
                redacted_target=bool(prior_entry.get("redacted_target", False)),
            )
        target_ref, redacted = _sanitize_target(request.target_type, request.target_id)
        phase_payload = _phase_payload(
            request=request,
            authority=authority,
            forget_tx_id=forget_tx_id,
            target_ref=target_ref,
            redacted_target=redacted,
        )
        boundary_previews = self._collect_boundary_previews(request)
        budget_previews, budget_blocked = self._budget_blockers(
            boundary_previews,
            request.defer_acknowledged,
        )
        if budget_previews:
            boundary_previews = list(boundary_previews) + budget_previews
        boundary_blocked = _boundary_blockers(boundary_previews, request.defer_acknowledged)
        try:
            self._validate_request(request)
            _append_phase(self.log_path, ForgetCommitPhase.PREPARED, phase_payload)
            if boundary_previews:
                _append_boundary_preview(self.log_path, phase_payload, boundary_previews, request.defer_acknowledged)
            if boundary_blocked:
                pressure_previews = _pressure_previews_for_entry(
                    boundary_previews,
                    request.defer_acknowledged,
                    budget_blocked,
                )
                self._record_pressure_with_budget(
                    phase_payload,
                    pressure_previews,
                    request.defer_acknowledged,
                )
                _append_boundary_refusal(
                    self.log_path,
                    phase_payload,
                    boundary_previews,
                    request.defer_acknowledged,
                )
                raise BoundaryRefusal(boundary_blocked)
            _append_phase(self.log_path, ForgetCommitPhase.APPLYING, phase_payload)
            outcome = self._apply_forget(request, authority=authority)
            post_state_hash = self._state_hash()
            authority_snapshot = build_authority_surface_snapshot_for_state(
                routine_registry=self.routine_registry,
                class_manager=self.class_manager,
            )
        except Exception as exc:
            _append_phase(self.log_path, ForgetCommitPhase.ABORTED, phase_payload, error_reason=str(exc))
            raise
        _append_phase(self.log_path, ForgetCommitPhase.COMMITTED, phase_payload)
        committed_entry = {
            "event": "intentional_forget",
            "target_type": request.target_type,
            "target": target_ref,
            "cascade": cascade,
            "authority": authority,
            "proof_level": request.proof_level,
            "forget_tx_id": forget_tx_id,
            "post_state_hash": post_state_hash,
            "redacted_target": redacted,
        }
        proof = _build_rollback_proof(
            forget_tx_id=forget_tx_id,
            authority_surface_hash=str(authority_snapshot.get("snapshot_hash", "")),
            narrative_summary_hash=_build_narrative_summary_hash(
                _with_entry(read_forget_log(self.log_path), committed_entry)
            ),
            semantic_domains=_semantic_domains_for_outcome(request, outcome),
            post_state_hash=post_state_hash,
        )
        committed_entry["rollback_proof_hash"] = proof["proof_hash"]
        append_json(self.log_path, committed_entry)
        if _find_forget_proof_entry(read_forget_log(self.log_path), forget_tx_id) is None:
            _append_rollback_proof(self.log_path, proof)
        self._clear_pressure_with_budget(phase_payload, reason="committed")
        self.verify_post_commit_invariants()
        return IntentionalForgetResult(
            target_type=request.target_type,
            target_id=request.target_id,
            forget_scope=request.forget_scope,
            proof_level=request.proof_level,
            timestamp=timestamp,
            forget_tx_id=forget_tx_id,
            replayed=False,
            cascade=cascade,
            post_state_hash=post_state_hash,
            impacted=tuple(outcome.removals),
            redacted_target=redacted,
        )

    def simulate_forget(
        self,
        request: IntentionalForgetRequest,
        *,
        authority: str = "operator",
    ) -> ForgetDiff:
        from sentientos import narrative_synthesis
        from sentientos.authority_surface import (
            build_authority_surface_snapshot_for_state,
            diff_authority_surfaces,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            simulation = self._clone_for_simulation(Path(temp_dir))
            pre_state_hash = simulation._state_hash()
            before_snapshot = build_authority_surface_snapshot_for_state(
                routine_registry=simulation.routine_registry,
                class_manager=simulation.class_manager,
            )
            boundary_previews = simulation._collect_boundary_previews(request)
            budget_previews, budget_blocked = simulation._budget_blockers(
                boundary_previews,
                request.defer_acknowledged,
            )
            if budget_previews:
                boundary_previews = list(boundary_previews) + budget_previews
            boundary_blocked = _boundary_blockers(boundary_previews, request.defer_acknowledged)
            if boundary_blocked:
                outcome = _ForgetOutcome()
                error_reason = "boundary_refusal"
                after_snapshot = before_snapshot
                post_state_hash = pre_state_hash
            else:
                outcome, error_reason = simulation._apply_forget_preview(request, authority=authority)
                after_snapshot = build_authority_surface_snapshot_for_state(
                    routine_registry=simulation.routine_registry,
                    class_manager=simulation.class_manager,
                )
                post_state_hash = simulation._state_hash()

        authority_diff = diff_authority_surfaces(before_snapshot, after_snapshot)
        target_ref, redacted = _sanitize_target(request.target_type, request.target_id)
        forget_tx_id = _build_forget_tx_id(
            request,
            authority=authority,
            target_ref=target_ref,
            target_set=_forget_target_set(request, target_ref),
            cascade_structure=self._cascade_structure_for_request(request),
        )
        replay_status = "already_applied" if _forget_tx_applied(self.log_path, forget_tx_id) else "new"
        phase_state = _phase_state_for_tx(read_forget_log(self.log_path), forget_tx_id)
        pressure_state = _pressure_state_for_tx(read_forget_log(self.log_path), forget_tx_id)
        budget_forecast = _pressure_budget_forecast(
            read_forget_log(self.log_path),
            self.pressure_budgets,
            boundary_previews,
            request.defer_acknowledged,
        )
        preview_entry = {
            "event": "intentional_forget",
            "target_type": request.target_type,
            "target": target_ref,
            "cascade": request.forget_scope == "cascade",
            "authority": authority,
            "proof_level": request.proof_level,
            "forget_tx_id": forget_tx_id,
            "post_state_hash": post_state_hash,
            "redacted_target": redacted,
        }
        forgetting_entries = read_forget_log(self.log_path)
        forgetting_entries.append(preview_entry)
        narrative_summary = narrative_synthesis.build_narrative_summary(
            since=None,
            source_from=None,
            source_to=None,
            now=datetime(1970, 1, 1, tzinfo=timezone.utc),
            log_output=False,
            forgetting_entries=forgetting_entries,
        )
        narrative_hash = _hash_payload(narrative_summary)
        narrative_summary_hashes = [
            {"view": narrative_summary.get("view", "narrative_summary"), "hash": narrative_hash}
        ]
        narrative_summary_hashes.append({"view": "forget_tx_id", "hash": _hash_reference(forget_tx_id)})

        blocked = outcome.blocked
        if error_reason and error_reason != "boundary_refusal":
            blocked = [{"target": request.target_type, "reason": error_reason}]
        if boundary_blocked:
            blocked = list(blocked) + boundary_blocked
        if replay_status == "already_applied":
            blocked = list(blocked) + [{"target": "forget_tx_id", "reason": "already_applied"}]
        invariant_violations = simulation._evaluate_post_commit_invariants(
            forgetting_entries=forgetting_entries
        )
        if invariant_violations:
            blocked = list(blocked) + [
                {"target": "post_commit_invariants", "reason": item["reason"]}
                for item in invariant_violations
            ]

        payload = {
            "view": "intentional_forget_diff",
            "schema_version": "forget_diff_v1",
            "request": {
                "target_type": request.target_type,
                "target_id": request.target_id,
                "forget_scope": request.forget_scope,
                "proof_level": request.proof_level,
                "authority": authority,
                "defer_acknowledged": request.defer_acknowledged,
            },
            "forget_tx_id": forget_tx_id,
            "replay_status": replay_status,
            "phase": phase_state.phase,
            "execution_status": phase_state.execution_status,
            "primary_targets": _sorted_unique(outcome.primary),
            "cascaded_removals": _sorted_unique(outcome.cascaded),
            "removals": _sorted_unique(outcome.removals),
            "authority_deltas": tuple(authority_diff.get("changes", ())),
            "blocked": _sorted_blockers(blocked),
            "skipped": _sorted_blockers(outcome.skipped),
            "narrative_summary_hashes": _sorted_hashes(narrative_summary_hashes),
            "state_hashes": {"before": pre_state_hash, "after": post_state_hash},
            "invariant_status": "violations" if invariant_violations else "ok",
            "invariant_violations": _sorted_blockers(invariant_violations),
            "boundary_previews": _sorted_boundary_previews(boundary_previews, request.defer_acknowledged),
            "pressure": _sorted_pressure_entries(pressure_state),
            "pressure_budgets": _sorted_pressure_budgets(budget_forecast),
        }
        diff_hash = _hash_payload(payload)
        return ForgetDiff(
            request=payload["request"],
            forget_tx_id=forget_tx_id,
            replay_status=replay_status,
            phase=phase_state.phase,
            execution_status=phase_state.execution_status,
            primary_targets=tuple(payload["primary_targets"]),
            cascaded_removals=tuple(payload["cascaded_removals"]),
            removals=tuple(payload["removals"]),
            authority_deltas=tuple(payload["authority_deltas"]),
            blocked=tuple(payload["blocked"]),
            skipped=tuple(payload["skipped"]),
            narrative_summary_hashes=tuple(payload["narrative_summary_hashes"]),
            state_hashes=payload["state_hashes"],
            invariant_status=payload["invariant_status"],
            invariant_violations=tuple(payload["invariant_violations"]),
            boundary_previews=tuple(payload["boundary_previews"]),
            pressure=tuple(payload["pressure"]),
            pressure_budgets=tuple(payload["pressure_budgets"]),
            diff_hash=diff_hash,
        )

    def _forget_routine(self, routine_id: str, *, cascade: bool, authority: str, outcome: _ForgetOutcome) -> None:
        target = f"routine:{routine_id}"
        if routine_id in self.routine_registry.list_forgotten():
            outcome.skipped.append({"target": target, "reason": "already_forgotten"})
        else:
            outcome.primary.append(target)
        if self.routine_registry.forget_routine(routine_id, forgotten_by=authority, reason="intentional_forget"):
            outcome.removals.append(target)
        if cascade and self.class_manager is not None:
            classes = sorted(self.class_manager.list_classes(), key=lambda item: item.name)
            for semantic_class in classes:
                if routine_id in semantic_class.routine_ids:
                    self.class_manager.remove_member(
                        semantic_class.name,
                        routine_id=routine_id,
                        removed_by=authority,
                        reason="routine_forgotten",
                    )
                    outcome.cascaded.append(f"semantic_class_member:{semantic_class.name}:{routine_id}")
                    outcome.removals.append(f"semantic_class_member:{semantic_class.name}:{routine_id}")
        if cascade and self.habit_engine is not None:
            habit_id = _habit_id_from_routine(routine_id)
            if habit_id:
                habit_target = f"habit:{habit_id}"
                if habit_id in self.habit_engine.list_forgotten():
                    outcome.skipped.append({"target": habit_target, "reason": "already_forgotten"})
                else:
                    outcome.cascaded.append(habit_target)
                if self.habit_engine.forget_habit(habit_id, forgotten_by=authority, reason="routine_forgotten"):
                    outcome.removals.append(habit_target)

    def _forget_habit(self, habit_id: str, *, cascade: bool, authority: str, outcome: _ForgetOutcome) -> None:
        if self.habit_engine is None:
            raise ValueError("Habit inference engine is required to forget habits")
        target = f"habit:{habit_id}"
        if habit_id in self.habit_engine.list_forgotten():
            outcome.skipped.append({"target": target, "reason": "already_forgotten"})
        else:
            outcome.primary.append(target)
        if self.habit_engine.forget_habit(habit_id, forgotten_by=authority, reason="intentional_forget"):
            outcome.removals.append(target)
        if cascade:
            routine_id = f"routine-{habit_id}"
            cascade_target = f"routine:{routine_id}"
            if routine_id in self.routine_registry.list_forgotten():
                outcome.skipped.append({"target": cascade_target, "reason": "already_forgotten"})
            else:
                outcome.cascaded.append(cascade_target)
            if self.routine_registry.forget_routine(routine_id, forgotten_by=authority, reason="habit_forgotten"):
                outcome.removals.append(cascade_target)

    def _forget_class(self, class_ref: str, *, cascade: bool, authority: str, outcome: _ForgetOutcome) -> None:
        if self.class_manager is None:
            raise ValueError("Semantic habit class manager is required to forget classes")
        semantic_class = self._resolve_class(class_ref)
        if semantic_class is None:
            target = f"class:{class_ref}"
            if class_ref in self.class_manager.list_forgotten():
                outcome.skipped.append({"target": target, "reason": "already_forgotten"})
            else:
                outcome.primary.append(target)
            self.class_manager.forget_class(class_ref, forgotten_by=authority, reason="intentional_forget")
            return
        target = f"class:{semantic_class.name}"
        if semantic_class.name in self.class_manager.list_forgotten():
            outcome.skipped.append({"target": target, "reason": "already_forgotten"})
        else:
            outcome.primary.append(target)
        self.class_manager.forget_class(semantic_class.name, forgotten_by=authority, reason="intentional_forget")
        outcome.removals.append(target)
        if cascade:
            for routine_id in sorted(semantic_class.routine_ids):
                cascade_target = f"routine:{routine_id}"
                if routine_id in self.routine_registry.list_forgotten():
                    outcome.skipped.append({"target": cascade_target, "reason": "already_forgotten"})
                else:
                    outcome.cascaded.append(cascade_target)
                if self.routine_registry.forget_routine(
                    routine_id,
                    forgotten_by=authority,
                    reason="semantic_class_forgotten",
                ):
                    outcome.removals.append(cascade_target)
                if self.habit_engine is not None:
                    habit_id = _habit_id_from_routine(routine_id)
                    if habit_id:
                        habit_target = f"habit:{habit_id}"
                        if habit_id in self.habit_engine.list_forgotten():
                            outcome.skipped.append({"target": habit_target, "reason": "already_forgotten"})
                        else:
                            outcome.cascaded.append(habit_target)
                        if self.habit_engine.forget_habit(
                            habit_id,
                            forgotten_by=authority,
                            reason="semantic_class_forgotten",
                        ):
                            outcome.removals.append(habit_target)

    def _forget_cognitive(self, target_id: str, *, authority: str, outcome: _ForgetOutcome) -> None:
        if self.cognitive_surface is None:
            raise ValueError("Cognitive surface is required to forget cognitive artifacts")
        if target_id in {"*", "all"}:
            outcome.primary.append("cognitive:all")
            removed = self.cognitive_surface.forget_all_preferences(
                forgotten_by=authority,
                reason="intentional_forget",
            )
            for key in sorted(removed):
                outcome.cascaded.append(f"cognitive:{key}")
                outcome.removals.append(f"cognitive:{key}")
            return
        target = f"cognitive:{target_id}"
        if target_id in self.cognitive_surface.list_forgotten_preferences():
            outcome.skipped.append({"target": target, "reason": "already_forgotten"})
        else:
            outcome.primary.append(target)
        removed = self.cognitive_surface.forget_preferences(
            [target_id],
            forgotten_by=authority,
            reason="intentional_forget",
        )
        for key in removed:
            outcome.removals.append(f"cognitive:{key}")

    def _forget_cor(self, hypothesis: str, *, authority: str, outcome: _ForgetOutcome) -> None:
        if self.cor_subsystem is None:
            raise ValueError("COR subsystem is required to forget hypotheses")
        target = f"cor:{_hash_reference(hypothesis)}"
        if hypothesis in self.cor_subsystem.list_forgotten():
            outcome.skipped.append({"target": target, "reason": "already_forgotten"})
        else:
            outcome.primary.append(target)
        if self.cor_subsystem.forget_hypothesis(hypothesis, reason="intentional_forget"):
            outcome.removals.append(target)

    def _forget_ssu(self, target_id: str, *, authority: str, outcome: _ForgetOutcome) -> None:
        if self.ssu is None:
            raise ValueError("SSU subsystem is required to forget symbols")
        key = self.ssu.parse_symbol_key(target_id)
        serialized = self.ssu.serialize_symbol_key(key)
        target = f"ssu:{_hash_reference(serialized)}"
        if key in self.ssu.list_forgotten():
            outcome.skipped.append({"target": target, "reason": "already_forgotten"})
        else:
            outcome.primary.append(target)
        if self.ssu.forget_symbol_key(key):
            outcome.removals.append(f"ssu:{serialized}")

    def _forget_all(self, *, cascade: bool, authority: str, outcome: _ForgetOutcome) -> None:
        routine_ids = sorted(self.routine_registry.list_routines(), key=lambda item: item.routine_id)
        for routine in routine_ids:
            routine_id = routine.routine_id
            target = f"routine:{routine_id}"
            if routine_id in self.routine_registry.list_forgotten():
                outcome.skipped.append({"target": target, "reason": "already_forgotten"})
            else:
                outcome.cascaded.append(target)
            if self.routine_registry.forget_routine(routine_id, forgotten_by=authority, reason="intentional_forget"):
                outcome.removals.append(target)
        if self.habit_engine is not None:
            for habit in sorted(self.habit_engine.list_habits(), key=lambda item: item.habit_id):
                habit_target = f"habit:{habit.habit_id}"
                if habit.habit_id in self.habit_engine.list_forgotten():
                    outcome.skipped.append({"target": habit_target, "reason": "already_forgotten"})
                else:
                    outcome.cascaded.append(habit_target)
                if self.habit_engine.forget_habit(
                    habit.habit_id,
                    forgotten_by=authority,
                    reason="intentional_forget_all",
                ):
                    outcome.removals.append(habit_target)
        if self.class_manager is not None:
            for semantic_class in sorted(self.class_manager.list_classes(), key=lambda item: item.name):
                class_target = f"class:{semantic_class.name}"
                if semantic_class.name in self.class_manager.list_forgotten():
                    outcome.skipped.append({"target": class_target, "reason": "already_forgotten"})
                else:
                    outcome.cascaded.append(class_target)
                if self.class_manager.forget_class(
                    semantic_class.name,
                    forgotten_by=authority,
                    reason="intentional_forget_all",
                ):
                    outcome.removals.append(class_target)
        if self.cor_subsystem is not None:
            for hypothesis in self.cor_subsystem.list_hypotheses():
                target = f"cor:{_hash_reference(hypothesis)}"
                if hypothesis in self.cor_subsystem.list_forgotten():
                    outcome.skipped.append({"target": target, "reason": "already_forgotten"})
                else:
                    outcome.cascaded.append(target)
                if self.cor_subsystem.forget_hypothesis(hypothesis, reason="intentional_forget_all"):
                    outcome.removals.append(target)
        if self.ssu is not None:
            for key in self.ssu.list_forgotten():
                serialized = self.ssu.serialize_symbol_key(key)
                outcome.cascaded.append(f"ssu:{_hash_reference(serialized)}")
            for key in self.ssu.list_symbol_records():
                serialized = self.ssu.serialize_symbol_key(key)
                target = f"ssu:{_hash_reference(serialized)}"
                if key in self.ssu.list_forgotten():
                    outcome.skipped.append({"target": target, "reason": "already_forgotten"})
                else:
                    outcome.cascaded.append(target)
                if self.ssu.forget_symbol_key(key):
                    outcome.removals.append(f"ssu:{serialized}")
        if self.cognitive_surface is not None:
            removed = self.cognitive_surface.forget_all_preferences(
                forgotten_by=authority,
                reason="intentional_forget_all",
            )
            for key in sorted(removed):
                outcome.cascaded.append(f"cognitive:{key}")
                outcome.removals.append(f"cognitive:{key}")
        if cascade and self.class_manager is not None:
            for semantic_class in sorted(self.class_manager.list_classes(), key=lambda item: item.name):
                for routine_id in sorted(semantic_class.routine_ids):
                    target = f"routine:{routine_id}"
                    if routine_id in self.routine_registry.list_forgotten():
                        outcome.skipped.append({"target": target, "reason": "already_forgotten"})
                    else:
                        outcome.cascaded.append(target)
                    if self.routine_registry.forget_routine(
                        routine_id,
                        forgotten_by=authority,
                        reason="intentional_forget_all",
                    ):
                        outcome.removals.append(target)

    def _apply_forget(self, request: IntentionalForgetRequest, *, authority: str) -> _ForgetOutcome:
        cascade = request.forget_scope == "cascade"
        outcome = _ForgetOutcome()
        if request.target_type == "all":
            outcome.primary.append("all")
            self._forget_all(cascade=cascade, authority=authority, outcome=outcome)
        elif request.target_type == "routine":
            self._forget_routine(request.target_id, cascade=cascade, authority=authority, outcome=outcome)
        elif request.target_type == "habit":
            self._forget_habit(request.target_id, cascade=cascade, authority=authority, outcome=outcome)
        elif request.target_type == "class":
            self._forget_class(request.target_id, cascade=cascade, authority=authority, outcome=outcome)
        elif request.target_type == "cognitive":
            self._forget_cognitive(request.target_id, authority=authority, outcome=outcome)
        elif request.target_type == "cor":
            self._forget_cor(request.target_id, authority=authority, outcome=outcome)
        elif request.target_type == "ssu":
            self._forget_ssu(request.target_id, authority=authority, outcome=outcome)
        else:
            raise ValueError(f"Unsupported forget target: {request.target_type}")
        return outcome

    def _apply_forget_preview(
        self, request: IntentionalForgetRequest, *, authority: str
    ) -> tuple[_ForgetOutcome, str | None]:
        try:
            return self._apply_forget(request, authority=authority), None
        except ValueError as exc:
            reason = _preview_error_reason(str(exc))
            return _ForgetOutcome(), reason

    def _clone_for_simulation(self, temp_root: Path) -> "IntentionalForgettingService":
        routine_registry = RoutineRegistry(
            store_path=temp_root / "routines.json",
            log_path=temp_root / "routine_log.jsonl",
        )
        routine_registry._state = copy.deepcopy(self.routine_registry._state)

        habit_engine = None
        if self.habit_engine is not None:
            habit_engine = _SilentHabitInferenceEngine(config=self.habit_engine.config)
            habit_engine._habits = copy.deepcopy(self.habit_engine._habits)
            habit_engine._proposal_status = copy.deepcopy(self.habit_engine._proposal_status)
            habit_engine._declined_habits = copy.deepcopy(self.habit_engine._declined_habits)
            habit_engine._approved_habits = copy.deepcopy(self.habit_engine._approved_habits)
            habit_engine._context_actions = copy.deepcopy(self.habit_engine._context_actions)
            habit_engine._context_outcomes = copy.deepcopy(self.habit_engine._context_outcomes)
            habit_engine._review_alerts = copy.deepcopy(self.habit_engine._review_alerts)
            habit_engine._forgotten_habits = set(self.habit_engine._forgotten_habits)

        class_manager = None
        if self.class_manager is not None:
            class_manager = SemanticHabitClassManager(
                registry=routine_registry,
                log_path=str(temp_root / "classes.jsonl"),
            )
            class_manager._classes = copy.deepcopy(self.class_manager._classes)
            class_manager._proposals = copy.deepcopy(self.class_manager._proposals)
            class_manager._declined_signatures = copy.deepcopy(self.class_manager._declined_signatures)
            class_manager._forgotten_classes = copy.deepcopy(self.class_manager._forgotten_classes)

        cor_subsystem = None
        if self.cor_subsystem is not None:
            cor_subsystem = _SilentCORSubsystem(
                config=self.cor_subsystem.config,
                adapters=(),
                now_fn=self.cor_subsystem._now,
            )
            cor_subsystem.context = copy.deepcopy(self.cor_subsystem.context)
            cor_subsystem._raw_events = copy.deepcopy(self.cor_subsystem._raw_events)
            cor_subsystem._hypothesis_history = copy.deepcopy(self.cor_subsystem._hypothesis_history)
            cor_subsystem._hypothesis_records = copy.deepcopy(self.cor_subsystem._hypothesis_records)
            cor_subsystem._proposal_suppression = copy.deepcopy(self.cor_subsystem._proposal_suppression)
            cor_subsystem._archived_proposals = copy.deepcopy(self.cor_subsystem._archived_proposals)
            cor_subsystem._global_silence_until = self.cor_subsystem._global_silence_until
            cor_subsystem._forgotten_hypotheses = set(self.cor_subsystem._forgotten_hypotheses)

        ssu = None
        if self.ssu is not None:
            ssu = SymbolicScreenUnderstanding(
                config=self.ssu.config,
                log_path=str(temp_root / "ssu.jsonl"),
                now_fn=self.ssu._now,
            )
            ssu._sequence = self.ssu._sequence
            ssu._symbol_records = copy.deepcopy(self.ssu._symbol_records)
            ssu._forgotten_symbols = set(self.ssu._forgotten_symbols)

        cognitive_surface = None
        if self.cognitive_surface is not None:
            cognitive_surface = CognitiveSurface(
                enabled=self.cognitive_surface.enabled,
                cache=None,
                default_expiration=self.cognitive_surface._default_expiration,
            )
            cognitive_surface._preferences = copy.deepcopy(self.cognitive_surface._preferences)
            cognitive_surface._preference_usage = list(self.cognitive_surface._preference_usage)
            cognitive_surface._forgotten_preferences = set(self.cognitive_surface._forgotten_preferences)

        return IntentionalForgettingService(
            routine_registry=routine_registry,
            habit_engine=habit_engine,
            class_manager=class_manager,
            cor_subsystem=cor_subsystem,
            ssu=ssu,
            cognitive_surface=cognitive_surface,
            log_path=temp_root / "forget_log.jsonl",
            boundary_contracts=self.boundary_contracts,
        )

    def _recover_incomplete_transactions(self) -> None:
        entries = read_forget_log(self.log_path)
        phases = _latest_phase_entries(entries)
        for forget_tx_id, phase_entry in phases.items():
            phase = phase_entry.get("phase")
            if phase not in {ForgetCommitPhase.PREPARED.value, ForgetCommitPhase.APPLYING.value}:
                continue
            if _forget_tx_applied(self.log_path, forget_tx_id):
                if phase != ForgetCommitPhase.COMMITTED.value:
                    _append_phase(self.log_path, ForgetCommitPhase.COMMITTED, dict(phase_entry))
                continue
            self._recover_transaction(phase_entry)

    def _recover_transaction(self, phase_entry: Mapping[str, object]) -> None:
        from sentientos.authority_surface import build_authority_surface_snapshot_for_state

        forget_tx_id = str(phase_entry.get("forget_tx_id", ""))
        if not forget_tx_id:
            return
        if _forget_tx_applied(self.log_path, forget_tx_id):
            return
        target_type = str(phase_entry.get("target_type", ""))
        target_ref = str(phase_entry.get("target", ""))
        authority = str(phase_entry.get("authority", "operator"))
        forget_scope = str(phase_entry.get("forget_scope", "exact"))
        proof_level = str(phase_entry.get("proof_level", "structural"))
        target_id = self._resolve_target_id(target_type, target_ref)
        if target_id is None and target_type not in {"all"}:
            _append_phase(
                self.log_path,
                ForgetCommitPhase.ABORTED,
                dict(phase_entry),
                error_reason="unresolved_target",
            )
            return
        request = IntentionalForgetRequest(
            target_type=target_type,
            target_id=target_id or target_ref,
            forget_scope=forget_scope,
            proof_level=proof_level,
        )
        phase_payload = _phase_payload(
            request=request,
            authority=authority,
            forget_tx_id=forget_tx_id,
            target_ref=target_ref,
            redacted_target=bool(phase_entry.get("redacted_target", False)),
        )
        boundary_previews = self._collect_boundary_previews(request)
        budget_previews, budget_blocked = self._budget_blockers(
            boundary_previews,
            request.defer_acknowledged,
        )
        if budget_previews:
            boundary_previews = list(boundary_previews) + budget_previews
        boundary_blocked = _boundary_blockers(boundary_previews, request.defer_acknowledged)
        try:
            self._validate_request(request)
            if boundary_previews:
                _append_boundary_preview(self.log_path, phase_payload, boundary_previews, request.defer_acknowledged)
            if boundary_blocked:
                pressure_previews = _pressure_previews_for_entry(
                    boundary_previews,
                    request.defer_acknowledged,
                    budget_blocked,
                )
                self._record_pressure_with_budget(
                    phase_payload,
                    pressure_previews,
                    request.defer_acknowledged,
                )
                _append_boundary_refusal(
                    self.log_path,
                    phase_payload,
                    boundary_previews,
                    request.defer_acknowledged,
                )
                raise BoundaryRefusal(boundary_blocked)
            if phase_entry.get("phase") == ForgetCommitPhase.PREPARED.value:
                _append_phase(self.log_path, ForgetCommitPhase.APPLYING, phase_payload)
            outcome = self._apply_forget(request, authority=authority)
            post_state_hash = self._state_hash()
            authority_snapshot = build_authority_surface_snapshot_for_state(
                routine_registry=self.routine_registry,
                class_manager=self.class_manager,
            )
        except Exception as exc:
            _append_phase(self.log_path, ForgetCommitPhase.ABORTED, phase_payload, error_reason=str(exc))
            return
        _append_phase(self.log_path, ForgetCommitPhase.COMMITTED, phase_payload)
        committed_entry = {
            "event": "intentional_forget",
            "target_type": request.target_type,
            "target": target_ref,
            "cascade": request.forget_scope == "cascade",
            "authority": authority,
            "proof_level": request.proof_level,
            "forget_tx_id": forget_tx_id,
            "post_state_hash": post_state_hash,
            "redacted_target": bool(phase_entry.get("redacted_target", False)),
        }
        proof = _build_rollback_proof(
            forget_tx_id=forget_tx_id,
            authority_surface_hash=str(authority_snapshot.get("snapshot_hash", "")),
            narrative_summary_hash=_build_narrative_summary_hash(
                _with_entry(read_forget_log(self.log_path), committed_entry)
            ),
            semantic_domains=_semantic_domains_for_outcome(request, outcome),
            post_state_hash=post_state_hash,
        )
        committed_entry["rollback_proof_hash"] = proof["proof_hash"]
        append_json(self.log_path, committed_entry)
        if _find_forget_proof_entry(read_forget_log(self.log_path), forget_tx_id) is None:
            _append_rollback_proof(self.log_path, proof)
        self._clear_pressure_with_budget(phase_payload, reason="committed")
        self.verify_post_commit_invariants()

    def reconcile_forgetting_pressure(self, *, forget_tx_id: str | None = None) -> list[dict[str, object]]:
        entries = read_forget_log(self.log_path)
        active_pressure = _active_pressure_entries(entries)
        reconciled: list[dict[str, object]] = []
        for pressure in active_pressure:
            pressure_id = str(pressure.get("forget_tx_id", ""))
            if forget_tx_id and pressure_id != forget_tx_id:
                continue
            target_type = str(pressure.get("target_type", ""))
            target_ref = str(pressure.get("target", ""))
            target_id = self._resolve_target_id(target_type, target_ref)
            if target_id is None and target_type != "all":
                reconciled.append({
                    "forget_tx_id": pressure_id,
                    "status": "blocked",
                    "phase": pressure.get("phase", "refused"),
                    "reason": "unresolved_target",
                })
                continue
            request = IntentionalForgetRequest(
                target_type=target_type,
                target_id=target_id or target_ref,
                forget_scope=str(pressure.get("forget_scope", "exact")),
                proof_level=str(pressure.get("proof_level", "structural")),
                defer_acknowledged=bool(pressure.get("defer_acknowledged", False)),
            )
            phase_payload = {
                "forget_tx_id": pressure_id,
                "target_type": target_type,
                "target": target_ref,
                "forget_scope": request.forget_scope,
                "proof_level": request.proof_level,
                "authority": str(pressure.get("authority", "operator")),
                "redacted_target": bool(pressure.get("redacted_target", False)),
                "defer_acknowledged": request.defer_acknowledged,
            }
            boundary_previews = self._collect_boundary_previews(request)
            budget_previews, budget_blocked = self._budget_blockers(
                boundary_previews,
                request.defer_acknowledged,
            )
            if budget_previews:
                boundary_previews = list(boundary_previews) + budget_previews
            boundary_blocked = _boundary_blockers(boundary_previews, request.defer_acknowledged)
            if not boundary_blocked:
                self._clear_pressure_with_budget(phase_payload, reason="reconciled")
                reconciled.append({
                    "forget_tx_id": pressure_id,
                    "status": "cleared",
                    "phase": "allowed",
                })
                continue
            pressure_previews = _pressure_previews_for_entry(
                boundary_previews,
                request.defer_acknowledged,
                budget_blocked,
            )
            new_pressure = None
            if pressure_previews:
                new_pressure = _pressure_entry_from_previews(
                    phase_payload,
                    pressure_previews,
                    request.defer_acknowledged,
                )
                self._append_pressure_with_budget(new_pressure)
            subsystems = (new_pressure or {}).get("subsystems", [])
            if not subsystems and budget_blocked:
                subsystems = [{"subsystem": name, "decision": "refuse"} for name in sorted(budget_blocked)]
            reconciled.append({
                "forget_tx_id": pressure_id,
                "status": "blocked",
                "phase": (new_pressure or {}).get("phase") or "budget_exceeded",
                "subsystems": subsystems,
            })
        return reconciled

    def _state_hash(self) -> str:
        snapshot = {
            "routines": sorted(self.routine_registry.list_forgotten()),
            "active_routines": sorted(routine.routine_id for routine in self.routine_registry.list_routines()),
        }
        if self.habit_engine is not None:
            snapshot["habits"] = sorted(record.habit_id for record in self.habit_engine.list_habits())
            snapshot["forgotten_habits"] = sorted(self.habit_engine.list_forgotten())
        if self.class_manager is not None:
            snapshot["semantic_classes"] = sorted(cls.name for cls in self.class_manager.list_classes())
            snapshot["forgotten_classes"] = sorted(self.class_manager.list_forgotten())
        if self.cor_subsystem is not None:
            snapshot["cor_hypotheses"] = sorted(
                _hash_reference(item) for item in self.cor_subsystem.list_hypotheses()
            )
            snapshot["cor_forgotten"] = sorted(
                _hash_reference(item) for item in self.cor_subsystem.list_forgotten()
            )
        if self.ssu is not None:
            snapshot["ssu_forgotten"] = sorted(
                _hash_reference(self.ssu.serialize_symbol_key(key)) for key in self.ssu.list_forgotten()
            )
        if self.cognitive_surface is not None:
            snapshot["cognitive_forgotten"] = sorted(self.cognitive_surface.list_forgotten_preferences())
        payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _resolve_class(self, class_ref: str) -> SemanticHabitClass | None:
        if self.class_manager is None:
            return None
        semantic_class = self.class_manager.get_class(class_ref)
        if semantic_class is not None:
            return semantic_class
        return self.class_manager.get_class_by_id(class_ref)

    def _resolve_target_id(self, target_type: str, target_ref: str) -> str | None:
        if target_type == "cor":
            if self.cor_subsystem is None:
                return None
            target_hash = target_ref.replace("hash:", "")
            for hypothesis in self.cor_subsystem.list_hypotheses():
                if _hash_reference(hypothesis) == target_hash:
                    return hypothesis
            for hypothesis in self.cor_subsystem.list_forgotten():
                if _hash_reference(hypothesis) == target_hash:
                    return hypothesis
            return None
        if target_type == "ssu":
            if self.ssu is None:
                return None
            target_hash = target_ref.replace("hash:", "")
            for key in self.ssu.list_symbol_records():
                serialized = self.ssu.serialize_symbol_key(key)
                if _hash_reference(serialized) == target_hash:
                    return serialized
            for key in self.ssu.list_forgotten():
                serialized = self.ssu.serialize_symbol_key(key)
                if _hash_reference(serialized) == target_hash:
                    return serialized
            return None
        return target_ref

    def _validate_request(self, request: IntentionalForgetRequest) -> None:
        if request.target_type not in {
            "all",
            "routine",
            "habit",
            "class",
            "cognitive",
            "cor",
            "ssu",
        }:
            raise ValueError(f"Unsupported forget target: {request.target_type}")
        if request.target_type == "habit" and self.habit_engine is None:
            raise ValueError("Habit inference engine is required to forget habits")
        if request.target_type == "class" and self.class_manager is None:
            raise ValueError("Semantic habit class manager is required to forget classes")
        if request.target_type == "cognitive" and self.cognitive_surface is None:
            raise ValueError("Cognitive surface is required to forget cognitive artifacts")
        if request.target_type == "cor" and self.cor_subsystem is None:
            raise ValueError("COR subsystem is required to forget hypotheses")
        if request.target_type == "ssu" and self.ssu is None:
            raise ValueError("SSU subsystem is required to forget symbols")

    def _forget_tx_id(self, request: IntentionalForgetRequest, *, authority: str) -> str:
        target_ref, _ = _sanitize_target(request.target_type, request.target_id)
        return _build_forget_tx_id(
            request,
            authority=authority,
            target_ref=target_ref,
            target_set=_forget_target_set(request, target_ref),
            cascade_structure=self._cascade_structure_for_request(request),
        )

    def _cascade_structure_for_request(self, request: IntentionalForgetRequest) -> dict[str, object]:
        cascade = request.forget_scope == "cascade"
        edges: set[tuple[str, str]] = set()
        nodes: set[str] = {request.target_type}
        if request.target_type == "all":
            nodes.update({
                "routine",
                "habit",
                "class",
                "cor",
                "ssu",
                "cognitive",
            })
        if cascade:
            if request.target_type == "routine":
                if self.class_manager is not None:
                    edges.add(("routine", "semantic_class_member"))
                    nodes.add("semantic_class_member")
                if self.habit_engine is not None:
                    edges.add(("routine", "habit"))
                    nodes.add("habit")
            elif request.target_type == "habit":
                edges.add(("habit", "routine"))
                nodes.add("routine")
            elif request.target_type == "class":
                edges.add(("class", "routine"))
                nodes.add("routine")
                if self.habit_engine is not None:
                    edges.add(("routine", "habit"))
                    nodes.add("habit")
            elif request.target_type == "all":
                edges.update({
                    ("all", "routine"),
                    ("all", "habit"),
                    ("all", "class"),
                    ("all", "cor"),
                    ("all", "ssu"),
                    ("all", "cognitive"),
                })
                nodes.update({
                    "routine",
                    "habit",
                    "class",
                    "cor",
                    "ssu",
                    "cognitive",
                })
        return {
            "cascade": cascade,
            "nodes": sorted(nodes),
            "edges": sorted([list(edge) for edge in edges]),
        }

    def verify_post_commit_invariants(self) -> None:
        violations = self._evaluate_post_commit_invariants()
        if violations:
            raise InvariantViolation(violations)

    def _evaluate_post_commit_invariants(
        self,
        *,
        forgetting_entries: Iterable[Mapping[str, object]] | None = None,
    ) -> list[dict[str, str]]:
        violations: list[dict[str, str]] = []
        boundary_state = {"state_hash": self._state_hash()}
        for verification in self._verify_boundary_contracts(boundary_state):
            if verification.status == "violation":
                violations.append({
                    "target": f"boundary:{verification.subsystem}",
                    "reason": verification.reason,
                })
        forgotten_routines = set(self.routine_registry.list_forgotten())
        active_routines = {routine.routine_id for routine in self.routine_registry.list_routines()}
        reintroduced_routines = sorted(forgotten_routines.intersection(active_routines))
        for routine_id in reintroduced_routines:
            violations.append({"target": f"routine:{routine_id}", "reason": "reintroduced_routine"})
        if self.habit_engine is not None:
            forgotten_habits = set(self.habit_engine.list_forgotten())
            active_habits = {habit.habit_id for habit in self.habit_engine.list_habits()}
            for habit_id in sorted(forgotten_habits.intersection(active_habits)):
                violations.append({"target": f"habit:{habit_id}", "reason": "reintroduced_habit"})
        if self.class_manager is not None:
            forgotten_classes = set(self.class_manager.list_forgotten())
            active_classes = {cls.name for cls in self.class_manager.list_classes()}
            for class_name in sorted(forgotten_classes.intersection(active_classes)):
                violations.append({"target": f"class:{class_name}", "reason": "reintroduced_class"})
            for semantic_class in sorted(self.class_manager.list_classes(), key=lambda item: item.name):
                for routine_id in sorted(semantic_class.routine_ids):
                    if routine_id in forgotten_routines:
                        violations.append({
                            "target": f"semantic_class_member:{semantic_class.name}:{routine_id}",
                            "reason": "semantic_class_rehydration",
                        })
        if self.cor_subsystem is not None:
            forgotten_hypotheses = set(self.cor_subsystem.list_forgotten())
            active_hypotheses = set(self.cor_subsystem.list_hypotheses())
            for hypothesis in sorted(forgotten_hypotheses.intersection(active_hypotheses)):
                violations.append({
                    "target": f"cor:{_hash_reference(hypothesis)}",
                    "reason": "reintroduced_cor",
                })
        if self.ssu is not None:
            forgotten_symbols = set(self.ssu.list_forgotten())
            active_symbols = set(self.ssu.list_symbol_records())
            for key in sorted(forgotten_symbols.intersection(active_symbols)):
                serialized = self.ssu.serialize_symbol_key(key)
                violations.append({
                    "target": f"ssu:{_hash_reference(serialized)}",
                    "reason": "reintroduced_ssu",
                })
        if self.cognitive_surface is not None:
            forgotten_preferences = set(self.cognitive_surface.list_forgotten_preferences())
            active_preferences = {pref.key for pref in self.cognitive_surface._preferences}
            for pref_key in sorted(forgotten_preferences.intersection(active_preferences)):
                violations.append({
                    "target": f"cognitive:{pref_key}",
                    "reason": "reintroduced_cognitive",
                })
        narrative_violations = _narrative_hash_violations(
            forgetting_entries or read_forget_log(self.log_path),
            self,
        )
        violations.extend(narrative_violations)
        return _sorted_blockers(violations)

    def _collect_boundary_previews(self, request: IntentionalForgetRequest) -> list[ForgetBoundaryPreview]:
        previews: list[ForgetBoundaryPreview] = []
        for contract in self.boundary_contracts:
            preview = _normalize_boundary_preview(contract.preview_forget(request), contract.name)
            if preview is not None:
                previews.append(preview)
        for name, subsystem in _boundary_subsystems(self):
            preview = _preview_from_subsystem(subsystem, name, request)
            if preview is not None:
                previews.append(preview)
        return previews

    def _verify_boundary_contracts(
        self,
        state: Mapping[str, object],
    ) -> list[ForgetBoundaryVerification]:
        verifications: list[ForgetBoundaryVerification] = []
        for contract in self.boundary_contracts:
            verification = _normalize_boundary_verification(contract.verify_post_commit(state), contract.name)
            if verification is not None:
                verifications.append(verification)
        for name, subsystem in _boundary_subsystems(self):
            verification = _verification_from_subsystem(subsystem, name, state)
            if verification is not None:
                verifications.append(verification)
        return verifications

    def _budget_blockers(
        self,
        previews: Sequence[ForgetBoundaryPreview],
        defer_acknowledged: bool,
    ) -> tuple[list[ForgetBoundaryPreview], set[str]]:
        if not self.pressure_budgets:
            return [], set()
        entries = read_forget_log(self.log_path)
        status = _pressure_budget_forecast(entries, self.pressure_budgets, previews, defer_acknowledged)
        exceeded = {
            item["subsystem"]
            for item in status
            if item.get("status") in {"exceeded", "would_exceed"}
        }
        if not exceeded:
            return [], set()
        impacted = _pressure_subsystems_from_previews(previews, defer_acknowledged)
        blocked = sorted(exceeded.intersection(impacted))
        if not blocked:
            return [], set()
        budget_previews = [
            ForgetBoundaryPreview(
                subsystem=subsystem,
                decision=ForgetBoundaryDecision.REFUSE,
                reason="pressure_budget_exceeded",
            )
            for subsystem in blocked
        ]
        return budget_previews, set(blocked)

    def _record_pressure_with_budget(
        self,
        phase_payload: Mapping[str, object],
        previews: Sequence[ForgetBoundaryPreview],
        defer_acknowledged: bool,
    ) -> None:
        if not previews:
            return
        before_entries = read_forget_log(self.log_path)
        _record_pressure_from_previews(self.log_path, phase_payload, previews, defer_acknowledged)
        after_entries = read_forget_log(self.log_path)
        _record_pressure_budget_transitions(
            self.log_path,
            before_entries,
            after_entries,
            self.pressure_budgets,
        )

    def _append_pressure_with_budget(self, entry: Mapping[str, object]) -> None:
        before_entries = read_forget_log(self.log_path)
        _append_pressure(self.log_path, entry)
        after_entries = read_forget_log(self.log_path)
        _record_pressure_budget_transitions(
            self.log_path,
            before_entries,
            after_entries,
            self.pressure_budgets,
        )

    def _clear_pressure_with_budget(self, phase_payload: Mapping[str, object], *, reason: str) -> None:
        before_entries = read_forget_log(self.log_path)
        _clear_pressure(self.log_path, phase_payload, reason=reason)
        after_entries = read_forget_log(self.log_path)
        _record_pressure_budget_transitions(
            self.log_path,
            before_entries,
            after_entries,
            self.pressure_budgets,
        )


def read_forget_log(path: Path | str = DEFAULT_LOG_PATH) -> list[dict[str, object]]:
    target = Path(path)
    if not target.exists():
        return []
    try:
        return read_json(target)
    except Exception:
        return []


def read_forget_pressure(path: Path | str = DEFAULT_LOG_PATH) -> list[dict[str, object]]:
    entries = read_forget_log(path)
    return _sorted_pressure_entries(_active_pressure_entries(entries))


def read_forget_pressure_budgets(
    path: Path | str = DEFAULT_LOG_PATH,
    *,
    budgets: Mapping[str, ForgetPressureBudget] | None = None,
) -> list[dict[str, object]]:
    entries = read_forget_log(path)
    return _sorted_pressure_budgets(_pressure_budget_status(entries, budgets or dict(DEFAULT_PRESSURE_BUDGETS)))


def build_forget_pressure_snapshot(
    path: Path | str = DEFAULT_LOG_PATH,
    *,
    budgets: Mapping[str, ForgetPressureBudget] | None = None,
) -> dict[str, object]:
    """Return a deterministic, redaction-safe pressure snapshot."""

    entries = read_forget_log(path)
    active_entries = _sorted_pressure_entries(_active_pressure_entries(entries))
    budget_status = _pressure_budget_status(entries, budgets or dict(DEFAULT_PRESSURE_BUDGETS))

    subsystem_counts: dict[str, int] = {}
    phase_counts: dict[str, int] = {}
    oldest_birth_index: int | None = None
    for entry in active_entries:
        phase = str(entry.get("phase", "unknown"))
        phase_counts[phase] = phase_counts.get(phase, 0) + 1
        birth_index = entry.get("pressure_birth_index")
        if isinstance(birth_index, int):
            oldest_birth_index = birth_index if oldest_birth_index is None else min(oldest_birth_index, birth_index)
        subsystems = entry.get("subsystems")
        if isinstance(subsystems, list):
            for subsystem in subsystems:
                if not isinstance(subsystem, Mapping):
                    continue
                name = subsystem.get("subsystem")
                if not name:
                    continue
                key = str(name)
                subsystem_counts[key] = subsystem_counts.get(key, 0) + 1

    pressure_by_subsystem = [
        {"subsystem": subsystem, "count": count} for subsystem, count in subsystem_counts.items()
    ]
    pressure_by_subsystem.sort(key=lambda item: item.get("subsystem", ""))

    overload_domains = []
    for item in budget_status:
        if item.get("status") != "exceeded":
            continue
        overload_domains.append({
            "subsystem": item.get("subsystem"),
            "outstanding": item.get("outstanding"),
        })
    overload_domains.sort(key=lambda item: str(item.get("subsystem", "")))

    current_index = len(entries) - 1 if entries else 0
    oldest_age = None
    if oldest_birth_index is not None:
        oldest_age = max(0, current_index - oldest_birth_index)

    snapshot = {
        "total_active_pressure": len(active_entries),
        "pressure_by_subsystem": pressure_by_subsystem,
        "phase_counts": dict(sorted(phase_counts.items(), key=lambda item: item[0])),
        "refusal_count": int(phase_counts.get("refused", 0)),
        "deferred_count": int(phase_counts.get("deferred", 0)),
        "overload": bool(overload_domains),
        "overload_domains": overload_domains,
        "oldest_unresolved_age": oldest_age,
    }
    snapshot["snapshot_hash"] = _hash_payload(snapshot)
    emit_introspection_event(
        event_type=EventType.FORGETTING_PRESSURE,
        phase="forgetting",
        summary="Forgetting pressure snapshot emitted.",
        metadata={
            "snapshot_hash": snapshot.get("snapshot_hash"),
            "total_active_pressure": snapshot.get("total_active_pressure"),
            "overload": snapshot.get("overload"),
            "oldest_unresolved_age": snapshot.get("oldest_unresolved_age"),
        },
        linked_artifact_ids=[str(snapshot.get("snapshot_hash", ""))],
    )
    return snapshot


def _sanitize_target(target_type: str, target_id: str) -> tuple[str, bool]:
    if target_type in {"cor", "ssu"}:
        return f"hash:{_hash_reference(target_id)}", True
    return target_id, False


def _habit_id_from_routine(routine_id: str) -> str | None:
    if routine_id.startswith("routine-habit-"):
        return routine_id[len("routine-") :]
    return None


def _hash_reference(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _hash_payload(payload: Mapping[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _build_forget_tx_id(
    request: IntentionalForgetRequest,
    *,
    authority: str,
    target_ref: str,
    target_set: Sequence[str],
    cascade_structure: Mapping[str, object],
) -> str:
    payload = {
        "proposal": {
            "target_type": request.target_type,
            "target_id": target_ref,
            "forget_scope": request.forget_scope,
            "proof_level": request.proof_level,
        },
        "authority": authority,
        "target_set": list(target_set),
        "cascade_structure": dict(cascade_structure),
        "defer_acknowledged": request.defer_acknowledged,
        "schema_version": "forget_tx_v1",
    }
    return _hash_payload(payload)


def _phase_payload(
    *,
    request: IntentionalForgetRequest,
    authority: str,
    forget_tx_id: str,
    target_ref: str,
    redacted_target: bool,
) -> dict[str, object]:
    return {
        "forget_tx_id": forget_tx_id,
        "target_type": request.target_type,
        "target": target_ref,
        "forget_scope": request.forget_scope,
        "proof_level": request.proof_level,
        "authority": authority,
        "redacted_target": redacted_target,
        "defer_acknowledged": request.defer_acknowledged,
    }


def _append_boundary_preview(
    log_path: Path,
    phase_payload: Mapping[str, object],
    previews: Sequence[ForgetBoundaryPreview],
    defer_acknowledged: bool,
) -> None:
    entry = dict(phase_payload)
    entry["event"] = "intentional_forget_boundary_preview"
    entry["timestamp"] = _now()
    entry["previews"] = _sorted_boundary_previews(previews, defer_acknowledged)
    append_json(log_path, entry)


def _append_boundary_refusal(
    log_path: Path,
    phase_payload: Mapping[str, object],
    previews: Sequence[ForgetBoundaryPreview],
    defer_acknowledged: bool,
) -> None:
    entry = dict(phase_payload)
    entry["event"] = "intentional_forget_refusal"
    entry["timestamp"] = _now()
    entry["previews"] = _sorted_boundary_previews(previews, defer_acknowledged)
    entry["blocked"] = _boundary_blockers(previews, defer_acknowledged)
    append_json(log_path, entry)


def _pressure_reason_hash(decision: ForgetBoundaryDecision, reason: str) -> str:
    return _hash_reference(f"{decision.value}:{reason}")


def _pressure_entry_from_previews(
    phase_payload: Mapping[str, object],
    previews: Sequence[ForgetBoundaryPreview],
    defer_acknowledged: bool,
) -> dict[str, object]:
    subsystems = []
    for preview in previews:
        if preview.decision == ForgetBoundaryDecision.ALLOW:
            continue
        if preview.decision == ForgetBoundaryDecision.DEFER and defer_acknowledged:
            continue
        subsystems.append({
            "subsystem": preview.subsystem,
            "decision": preview.decision.value,
            "reason_hash": _pressure_reason_hash(preview.decision, preview.reason),
        })
    phase = "refused" if any(item["decision"] == ForgetBoundaryDecision.REFUSE.value for item in subsystems) else "deferred"
    pressure_weight = _pressure_weight_for_previews(subsystems)
    entry = {
        "event": "intentional_forget_pressure",
        "forget_tx_id": phase_payload.get("forget_tx_id"),
        "target_type": phase_payload.get("target_type"),
        "target": phase_payload.get("target"),
        "forget_scope": phase_payload.get("forget_scope"),
        "proof_level": phase_payload.get("proof_level"),
        "authority": phase_payload.get("authority"),
        "redacted_target": bool(phase_payload.get("redacted_target", False)),
        "defer_acknowledged": bool(phase_payload.get("defer_acknowledged", False)),
        "status": "active",
        "phase": phase,
        "subsystems": _sorted_pressure_subsystems(subsystems),
        "pressure_weight": pressure_weight,
    }
    entry["pressure_hash"] = _hash_payload(entry)
    return entry


def _record_pressure_from_previews(
    log_path: Path,
    phase_payload: Mapping[str, object],
    previews: Sequence[ForgetBoundaryPreview],
    defer_acknowledged: bool,
) -> None:
    entry = _pressure_entry_from_previews(phase_payload, previews, defer_acknowledged)
    _append_pressure(log_path, entry)


def _clear_pressure(log_path: Path, phase_payload: Mapping[str, object], *, reason: str) -> None:
    entries = read_forget_log(log_path)
    latest = _latest_pressure_entries(entries).get(str(phase_payload.get("forget_tx_id", "")))
    if not latest or latest.get("status") != "active":
        return
    cleared = {
        "event": "intentional_forget_pressure",
        "forget_tx_id": phase_payload.get("forget_tx_id"),
        "target_type": phase_payload.get("target_type"),
        "target": phase_payload.get("target"),
        "forget_scope": phase_payload.get("forget_scope"),
        "proof_level": phase_payload.get("proof_level"),
        "authority": phase_payload.get("authority"),
        "redacted_target": bool(phase_payload.get("redacted_target", False)),
        "defer_acknowledged": bool(phase_payload.get("defer_acknowledged", False)),
        "status": "cleared",
        "phase": reason,
        "subsystems": [],
    }
    cleared["pressure_hash"] = _hash_payload(cleared)
    _append_pressure(log_path, cleared)


def _append_phase(
    log_path: Path,
    phase: ForgetCommitPhase,
    payload: Mapping[str, object],
    *,
    error_reason: str | None = None,
) -> None:
    entry = dict(payload)
    entry["event"] = "intentional_forget_phase"
    entry["phase"] = phase.value
    entry["timestamp"] = _now()
    if error_reason:
        entry["error_reason"] = error_reason
    append_json(log_path, entry)


def _append_pressure(log_path: Path, entry: Mapping[str, object]) -> None:
    entries = read_forget_log(log_path)
    latest = _latest_pressure_entries(entries).get(str(entry.get("forget_tx_id", "")))
    if latest and latest.get("pressure_hash") == entry.get("pressure_hash"):
        return
    payload = dict(entry)
    payload["timestamp"] = _now()
    payload["pressure_log_index"] = len(entries)
    if latest and latest.get("pressure_birth_index") is not None:
        payload["pressure_birth_index"] = latest.get("pressure_birth_index")
    else:
        payload["pressure_birth_index"] = payload["pressure_log_index"]
    if latest:
        payload["action"] = _pressure_action(latest, entry)
    else:
        payload["action"] = "created"
    append_json(log_path, payload)


def _pressure_action(previous: Mapping[str, object], current: Mapping[str, object]) -> str:
    if current.get("status") == "cleared":
        return "cleared"
    if previous.get("status") == "active" and current.get("status") == "active":
        if previous.get("phase") == "deferred" and current.get("phase") == "refused":
            return "escalated"
        return "reaffirmed"
    return "updated"


def _latest_phase_entries(entries: Iterable[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    latest: dict[str, dict[str, object]] = {}
    for entry in entries:
        if entry.get("event") != "intentional_forget_phase":
            continue
        forget_tx_id = entry.get("forget_tx_id")
        if not forget_tx_id:
            continue
        latest[str(forget_tx_id)] = dict(entry)
    return latest


def _latest_pressure_entries(entries: Iterable[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    latest: dict[str, dict[str, object]] = {}
    for entry in entries:
        if entry.get("event") != "intentional_forget_pressure":
            continue
        forget_tx_id = entry.get("forget_tx_id")
        if not forget_tx_id:
            continue
        latest[str(forget_tx_id)] = dict(entry)
    return latest


def _pressure_state_for_tx(
    entries: Iterable[Mapping[str, object]],
    forget_tx_id: str,
) -> list[dict[str, object]]:
    latest = _latest_pressure_entries(entries).get(forget_tx_id)
    if not latest or latest.get("status") != "active":
        return []
    return [dict(latest)]


def _active_pressure_entries(entries: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    latest = _latest_pressure_entries(entries)
    return [dict(entry) for entry in latest.values() if entry.get("status") == "active"]


def _phase_state_for_tx(entries: Iterable[Mapping[str, object]], forget_tx_id: str) -> _ForgetPhaseState:
    phase_entry = None
    for entry in entries:
        if entry.get("event") != "intentional_forget_phase":
            continue
        if entry.get("forget_tx_id") == forget_tx_id:
            phase_entry = entry
    if phase_entry is None:
        return _ForgetPhaseState(phase=None, execution_status="none")
    phase = str(phase_entry.get("phase")) if phase_entry.get("phase") is not None else None
    if phase in {ForgetCommitPhase.PREPARED.value, ForgetCommitPhase.APPLYING.value}:
        status = "pending"
    elif phase == ForgetCommitPhase.COMMITTED.value:
        status = "committed"
    elif phase == ForgetCommitPhase.ABORTED.value:
        status = "aborted"
    else:
        status = "unknown"
    return _ForgetPhaseState(phase=phase, execution_status=status)


def _preview_error_reason(message: str) -> str:
    if message.startswith("Unsupported forget target:"):
        return "unsupported_target"
    mapping = {
        "Habit inference engine is required to forget habits": "missing_habit_engine",
        "Semantic habit class manager is required to forget classes": "missing_class_manager",
        "Cognitive surface is required to forget cognitive artifacts": "missing_cognitive_surface",
        "COR subsystem is required to forget hypotheses": "missing_cor",
        "SSU subsystem is required to forget symbols": "missing_ssu",
    }
    return mapping.get(message, "blocked")


def _sorted_unique(values: Iterable[str]) -> list[str]:
    return sorted(set(values))


def _sorted_blockers(items: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    normalized = [dict(item) for item in items]
    normalized.sort(key=lambda item: (item.get("target", ""), item.get("reason", "")))
    return normalized


def _sorted_hashes(items: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    normalized = [dict(item) for item in items]
    normalized.sort(key=lambda item: (item.get("view", ""), item.get("hash", "")))
    return normalized


def _sorted_pressure_subsystems(items: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    normalized = [dict(item) for item in items]
    normalized.sort(key=lambda item: (item.get("subsystem", ""), item.get("decision", "")))
    return normalized


def _sorted_pressure_entries(items: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    normalized = [dict(item) for item in items]
    normalized.sort(key=lambda item: str(item.get("forget_tx_id", "")))
    return normalized


def _sorted_pressure_budgets(items: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    normalized = [dict(item) for item in items]
    normalized.sort(key=lambda item: (item.get("subsystem", ""), str(item.get("status", ""))))
    return normalized


def _sorted_boundary_previews(
    previews: Iterable[ForgetBoundaryPreview],
    defer_acknowledged: bool,
) -> list[dict[str, object]]:
    normalized = [
        {
            "subsystem": preview.subsystem,
            "decision": preview.decision.value,
            "reason": preview.reason,
            "acknowledged": bool(defer_acknowledged) if preview.decision == ForgetBoundaryDecision.DEFER else False,
        }
        for preview in previews
    ]
    normalized.sort(key=lambda item: (item.get("subsystem", ""), item.get("decision", "")))
    return normalized


def _boundary_blockers(
    previews: Iterable[ForgetBoundaryPreview],
    defer_acknowledged: bool,
) -> list[dict[str, str]]:
    blocked: list[dict[str, str]] = []
    for preview in previews:
        if preview.decision == ForgetBoundaryDecision.ALLOW:
            continue
        if preview.decision == ForgetBoundaryDecision.DEFER and defer_acknowledged:
            continue
        blocked.append({
            "target": f"boundary:{preview.subsystem}",
            "reason": f"{preview.decision.value}:{preview.reason}",
        })
    return _sorted_blockers(blocked)


def _pressure_weight_for_previews(subsystems: Sequence[Mapping[str, str]]) -> float:
    return float(max(1, len(subsystems)))


def _pressure_subsystems_from_previews(
    previews: Sequence[ForgetBoundaryPreview],
    defer_acknowledged: bool,
) -> set[str]:
    subsystems: set[str] = set()
    for preview in previews:
        if preview.decision == ForgetBoundaryDecision.ALLOW:
            continue
        if preview.decision == ForgetBoundaryDecision.DEFER and defer_acknowledged:
            continue
        subsystems.add(preview.subsystem)
    return subsystems


def _pressure_previews_for_entry(
    previews: Sequence[ForgetBoundaryPreview],
    defer_acknowledged: bool,
    budget_blocked: Iterable[str],
) -> list[ForgetBoundaryPreview]:
    blocked = set(budget_blocked)
    return [
        preview
        for preview in previews
        if preview.subsystem not in blocked and preview.reason != "pressure_budget_exceeded"
    ]


def _pressure_budget_for_subsystem(
    budgets: Mapping[str, ForgetPressureBudget],
    subsystem: str,
) -> ForgetPressureBudget | None:
    return budgets.get(subsystem) or budgets.get("default")


def _pressure_budget_status(
    entries: Iterable[Mapping[str, object]],
    budgets: Mapping[str, ForgetPressureBudget],
) -> list[dict[str, object]]:
    entries_list = [dict(entry) for entry in entries]
    active_entries = _active_pressure_entries(entries_list)
    current_index = len(entries_list)
    status: dict[str, dict[str, object]] = {}
    for entry in active_entries:
        weight = float(entry.get("pressure_weight", 1.0) or 1.0)
        birth_index = entry.get("pressure_birth_index")
        if birth_index is None:
            birth_index = entry.get("pressure_log_index") or 0
        try:
            birth_index = int(birth_index)
        except (TypeError, ValueError):
            birth_index = 0
        age = max(0, current_index - birth_index)
        for subsystem_entry in entry.get("subsystems", []) or []:
            subsystem = str(subsystem_entry.get("subsystem", ""))
            if not subsystem:
                continue
            budget = _pressure_budget_for_subsystem(budgets, subsystem)
            if budget is None:
                continue
            metrics = status.setdefault(subsystem, {
                "subsystem": subsystem,
                "outstanding": 0,
                "total_weight": 0.0,
                "oldest_duration": 0,
                "budget": budget.to_dict(),
                "exceeded": False,
                "status": "ok",
                "exceeded_reasons": [],
            })
            metrics["outstanding"] = int(metrics["outstanding"]) + 1
            metrics["total_weight"] = float(metrics["total_weight"]) + weight
            metrics["oldest_duration"] = max(int(metrics["oldest_duration"]), int(age))
    for subsystem, metrics in status.items():
        budget = _pressure_budget_for_subsystem(budgets, subsystem)
        if budget is None:
            continue
        reasons: list[str] = []
        if budget.max_outstanding is not None and int(metrics["outstanding"]) > budget.max_outstanding:
            reasons.append("max_outstanding")
        if budget.max_duration is not None and int(metrics["oldest_duration"]) > budget.max_duration:
            reasons.append("max_duration")
        if budget.max_weight is not None and float(metrics["total_weight"]) > budget.max_weight:
            reasons.append("max_weight")
        if reasons:
            metrics["exceeded"] = True
            metrics["status"] = "exceeded"
            metrics["exceeded_reasons"] = reasons
        else:
            metrics["exceeded"] = False
            metrics["status"] = "ok"
            metrics["exceeded_reasons"] = []
    return list(status.values())


def _pressure_budget_forecast(
    entries: Iterable[Mapping[str, object]],
    budgets: Mapping[str, ForgetPressureBudget],
    previews: Sequence[ForgetBoundaryPreview],
    defer_acknowledged: bool,
) -> list[dict[str, object]]:
    entries_list = [dict(entry) for entry in entries]
    base_status = {item["subsystem"]: dict(item) for item in _pressure_budget_status(entries_list, budgets)}
    prospective_subsystems = _pressure_subsystems_from_previews(previews, defer_acknowledged)
    if prospective_subsystems:
        synthetic_entry = {
            "event": "intentional_forget_pressure",
            "forget_tx_id": "budget_forecast",
            "status": "active",
            "pressure_weight": _pressure_weight_for_previews([{"subsystem": name} for name in prospective_subsystems]),
            "pressure_birth_index": len(entries_list),
            "subsystems": [{"subsystem": name} for name in sorted(prospective_subsystems)],
        }
        entries_list.append(synthetic_entry)
    forecast = {item["subsystem"]: dict(item) for item in _pressure_budget_status(entries_list, budgets)}
    combined: list[dict[str, object]] = []
    subsystems = sorted(set(base_status.keys()).union(forecast.keys()))
    for subsystem in subsystems:
        future = forecast.get(subsystem)
        if not future:
            continue
        current = base_status.get(subsystem)
        status = "ok"
        if future.get("exceeded"):
            if current and current.get("exceeded"):
                status = "exceeded"
            else:
                status = "would_exceed"
        future = dict(future)
        future["status"] = status
        combined.append(future)
    return combined


def _append_pressure_budget_event(
    log_path: Path,
    *,
    subsystem: str,
    status: str,
    payload: Mapping[str, object],
) -> None:
    entry = {
        "event": "intentional_forget_pressure_budget",
        "timestamp": _now(),
        "subsystem": subsystem,
        "status": status,
        "budget": payload.get("budget", {}),
        "outstanding": payload.get("outstanding", 0),
        "total_weight": payload.get("total_weight", 0.0),
        "oldest_duration": payload.get("oldest_duration", 0),
        "exceeded_reasons": payload.get("exceeded_reasons", []),
    }
    entry["budget_hash"] = _hash_payload(entry)
    append_json(log_path, entry)


def _record_pressure_budget_transitions(
    log_path: Path,
    before_entries: Iterable[Mapping[str, object]],
    after_entries: Iterable[Mapping[str, object]],
    budgets: Mapping[str, ForgetPressureBudget],
) -> None:
    before = {item["subsystem"]: dict(item) for item in _pressure_budget_status(before_entries, budgets)}
    after = {item["subsystem"]: dict(item) for item in _pressure_budget_status(after_entries, budgets)}
    subsystems = sorted(set(before.keys()).union(after.keys()))
    for subsystem in subsystems:
        before_exceeded = bool(before.get(subsystem, {}).get("exceeded"))
        after_payload = after.get(subsystem)
        after_exceeded = bool(after_payload.get("exceeded")) if after_payload else False
        if before_exceeded == after_exceeded:
            continue
        status = "exceeded" if after_exceeded else "cleared"
        payload = after_payload or before.get(subsystem, {})
        if payload:
            _append_pressure_budget_event(log_path, subsystem=subsystem, status=status, payload=payload)


def _forget_target_set(request: IntentionalForgetRequest, target_ref: str) -> tuple[str, ...]:
    if request.target_type == "all":
        return ("all",)
    return (f"{request.target_type}:{target_ref}",)


def _forget_tx_applied(log_path: Path, forget_tx_id: str) -> bool:
    return _find_forget_tx_entry(read_forget_log(log_path), forget_tx_id) is not None


def _find_forget_tx_entry(
    entries: Iterable[Mapping[str, object]],
    forget_tx_id: str,
) -> dict[str, object] | None:
    for entry in entries:
        if entry.get("event") != "intentional_forget":
            continue
        if entry.get("forget_tx_id") == forget_tx_id:
            return dict(entry)
    return None


def _build_narrative_summary_hash(entries: Iterable[Mapping[str, object]]) -> str:
    from sentientos import narrative_synthesis

    stable_entries = _stable_forget_entries(entries)
    summary = narrative_synthesis.build_narrative_summary(
        since=None,
        source_from=None,
        source_to=None,
        now=datetime(1970, 1, 1, tzinfo=timezone.utc),
        log_output=False,
        forgetting_entries=stable_entries,
    )
    return _hash_payload(summary)


def _build_rollback_proof(
    *,
    forget_tx_id: str,
    authority_surface_hash: str,
    narrative_summary_hash: str,
    semantic_domains: Sequence[str],
    post_state_hash: str,
) -> dict[str, object]:
    payload = {
        "view": "intentional_forget_rollback_proof",
        "schema_version": "forget_rollback_proof_v1",
        "forget_tx_id": forget_tx_id,
        "authority_surface_hash": authority_surface_hash,
        "narrative_summary_hash": narrative_summary_hash,
        "semantic_domains": list(semantic_domains),
        "post_state_hash": post_state_hash,
    }
    proof_hash = _hash_payload(payload)
    payload["proof_hash"] = proof_hash
    return payload


def _append_rollback_proof(log_path: Path, proof: Mapping[str, object]) -> None:
    entry = dict(proof)
    entry["event"] = "intentional_forget_rollback_proof"
    entry["timestamp"] = _now()
    append_json(log_path, entry)


def _find_forget_proof_entry(
    entries: Iterable[Mapping[str, object]],
    forget_tx_id: str,
) -> dict[str, object] | None:
    for entry in entries:
        if entry.get("event") != "intentional_forget_rollback_proof":
            continue
        if entry.get("forget_tx_id") == forget_tx_id:
            return dict(entry)
    return None


def _semantic_domains_for_outcome(
    request: IntentionalForgetRequest,
    outcome: _ForgetOutcome,
) -> list[str]:
    domains = {request.target_type}
    for entry in outcome.primary + outcome.cascaded + outcome.removals:
        if entry.startswith("routine:"):
            domains.add("routine")
        elif entry.startswith("habit:"):
            domains.add("habit")
        elif entry.startswith("class:"):
            domains.add("class")
        elif entry.startswith("semantic_class_member:"):
            domains.add("class")
            domains.add("routine")
        elif entry.startswith("cor:"):
            domains.add("cor")
        elif entry.startswith("ssu:"):
            domains.add("ssu")
        elif entry.startswith("cognitive:"):
            domains.add("cognitive")
        elif entry == "all":
            domains.add("all")
    return sorted(domains)


def _narrative_hash_violations(
    entries: Iterable[Mapping[str, object]],
    service: IntentionalForgettingService,
) -> list[dict[str, str]]:
    if service.cor_subsystem is None and service.ssu is None:
        return []
    forgotten_hashes: list[str] = []
    if service.cor_subsystem is not None:
        forgotten_hashes.extend(_hash_reference(item) for item in service.cor_subsystem.list_forgotten())
    if service.ssu is not None:
        forgotten_hashes.extend(
            _hash_reference(service.ssu.serialize_symbol_key(key)) for key in service.ssu.list_forgotten()
        )
    if not forgotten_hashes:
        return []
    from sentientos import narrative_synthesis

    stable_entries = _stable_forget_entries(entries)
    summary = narrative_synthesis.build_narrative_summary(
        since=None,
        source_from=None,
        source_to=None,
        now=datetime(1970, 1, 1, tzinfo=timezone.utc),
        log_output=False,
        forgetting_entries=stable_entries,
    )
    payload = json.dumps(summary, sort_keys=True)
    violations = []
    for forgotten_hash in forgotten_hashes:
        if forgotten_hash in payload:
            violations.append({"target": f"hash:{forgotten_hash}", "reason": "narrative_hash_leak"})
    return violations


def _with_entry(entries: Iterable[Mapping[str, object]], entry: Mapping[str, object]) -> list[dict[str, object]]:
    combined = [dict(item) for item in entries]
    combined.append(dict(entry))
    return combined


def _stable_forget_entries(entries: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    stable_entries: list[dict[str, object]] = []
    for entry in entries:
        cleaned = {key: value for key, value in entry.items() if key not in {"timestamp", "prev_hash", "rolling_hash"}}
        stable_entries.append(cleaned)
    return stable_entries


def _boundary_subsystems(
    service: IntentionalForgettingService,
) -> Iterable[tuple[str, object]]:
    candidates = [
        ("routine_registry", service.routine_registry),
        ("habit_engine", service.habit_engine),
        ("class_manager", service.class_manager),
        ("cor_subsystem", service.cor_subsystem),
        ("ssu", service.ssu),
        ("cognitive_surface", service.cognitive_surface),
    ]
    return [(name, subsystem) for name, subsystem in candidates if subsystem is not None]


def _preview_from_subsystem(
    subsystem: object,
    name: str,
    request: IntentionalForgetRequest,
) -> ForgetBoundaryPreview | None:
    preview_fn = getattr(subsystem, "preview_forget", None)
    if preview_fn is None:
        return None
    return _normalize_boundary_preview(preview_fn(request), name)


def _verification_from_subsystem(
    subsystem: object,
    name: str,
    state: Mapping[str, object],
) -> ForgetBoundaryVerification | None:
    verify_fn = getattr(subsystem, "verify_post_commit", None)
    if verify_fn is None:
        return None
    return _normalize_boundary_verification(verify_fn(state), name)


def _parse_boundary_decision(value: object) -> ForgetBoundaryDecision | None:
    if isinstance(value, ForgetBoundaryDecision):
        return value
    if isinstance(value, str):
        try:
            return ForgetBoundaryDecision(value)
        except ValueError:
            return None
    return None


def _normalize_boundary_preview(
    preview: object,
    default_subsystem: str,
) -> ForgetBoundaryPreview | None:
    if preview is None:
        return None
    if isinstance(preview, ForgetBoundaryPreview):
        subsystem = preview.subsystem or default_subsystem
        return ForgetBoundaryPreview(
            subsystem=subsystem,
            decision=preview.decision,
            reason=preview.reason,
        )
    if isinstance(preview, Mapping):
        decision = _parse_boundary_decision(preview.get("decision"))
        reason = str(preview.get("reason", ""))
        subsystem = str(preview.get("subsystem") or default_subsystem)
        if decision is None:
            return None
        return ForgetBoundaryPreview(subsystem=subsystem, decision=decision, reason=reason)
    if isinstance(preview, (tuple, list)) and len(preview) >= 2:
        decision = _parse_boundary_decision(preview[0])
        reason = str(preview[1])
        if decision is None:
            return None
        return ForgetBoundaryPreview(subsystem=default_subsystem, decision=decision, reason=reason)
    return None


def _normalize_boundary_verification(
    verification: object,
    default_subsystem: str,
) -> ForgetBoundaryVerification | None:
    if verification is None:
        return None
    if isinstance(verification, ForgetBoundaryVerification):
        subsystem = verification.subsystem or default_subsystem
        return ForgetBoundaryVerification(
            subsystem=subsystem,
            status=verification.status,
            reason=verification.reason,
        )
    if isinstance(verification, Mapping):
        status = str(verification.get("status", ""))
        reason = str(verification.get("reason", ""))
        subsystem = str(verification.get("subsystem") or default_subsystem)
        if not status:
            return None
        return ForgetBoundaryVerification(subsystem=subsystem, status=status, reason=reason)
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "ForgetDiff",
    "ForgetCommitPhase",
    "ForgetBoundaryContract",
    "ForgetBoundaryDecision",
    "ForgetBoundaryPreview",
    "ForgetBoundaryVerification",
    "ForgetPressureSignal",
    "ForgetPressureBudget",
    "BoundaryRefusal",
    "IntentionalForgetRequest",
    "IntentionalForgetResult",
    "IntentionalForgettingService",
    "DEFAULT_LOG_PATH",
    "DEFAULT_PRESSURE_BUDGETS",
    "read_forget_log",
    "read_forget_pressure",
    "read_forget_pressure_budgets",
    "build_forget_pressure_snapshot",
]
