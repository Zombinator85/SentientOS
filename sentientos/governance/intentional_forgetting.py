from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from logging_config import get_log_path
from log_utils import append_json, read_json
from sentientos.cognition.surface import CognitiveSurface
from sentientos.cor import CORSubsystem
from sentientos.governance.habit_inference import HabitInferenceEngine
from sentientos.governance.routine_delegation import RoutineRegistry
from sentientos.governance.semantic_habit_class import SemanticHabitClass, SemanticHabitClassManager
from sentientos.ssu import SymbolicScreenUnderstanding


DEFAULT_LOG_PATH = get_log_path("intentional_forgetting.jsonl", "INTENTIONAL_FORGET_LOG")


@dataclass(frozen=True)
class IntentionalForgetRequest:
    target_type: str
    target_id: str
    forget_scope: str
    proof_level: str


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


@dataclass(frozen=True)
class ForgetDiff:
    request: Mapping[str, str]
    forget_tx_id: str
    replay_status: str
    primary_targets: tuple[str, ...]
    cascaded_removals: tuple[str, ...]
    removals: tuple[str, ...]
    authority_deltas: tuple[dict[str, object], ...]
    blocked: tuple[dict[str, str], ...]
    skipped: tuple[dict[str, str], ...]
    narrative_summary_hashes: tuple[dict[str, str], ...]
    state_hashes: Mapping[str, str]
    diff_hash: str

    def to_dict(self) -> dict[str, object]:
        return {
            "view": "intentional_forget_diff",
            "request": dict(self.request),
            "forget_tx_id": self.forget_tx_id,
            "replay_status": self.replay_status,
            "primary_targets": list(self.primary_targets),
            "cascaded_removals": list(self.cascaded_removals),
            "removals": list(self.removals),
            "authority_deltas": [dict(item) for item in self.authority_deltas],
            "blocked": [dict(item) for item in self.blocked],
            "skipped": [dict(item) for item in self.skipped],
            "narrative_summary_hashes": [dict(item) for item in self.narrative_summary_hashes],
            "state_hashes": dict(self.state_hashes),
            "diff_hash": self.diff_hash,
        }


@dataclass
class _ForgetOutcome:
    primary: list[str] = field(default_factory=list)
    cascaded: list[str] = field(default_factory=list)
    removals: list[str] = field(default_factory=list)
    blocked: list[dict[str, str]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)


class _SilentHabitInferenceEngine(HabitInferenceEngine):
    def _log_event(self, kind: str, payload: Mapping[str, object]) -> None:
        return None


class _SilentCORSubsystem(CORSubsystem):
    def _log_event(self, kind: str, payload: dict[str, object]) -> None:
        return None


@dataclass
class IntentionalForgettingService:
    routine_registry: RoutineRegistry = field(default_factory=RoutineRegistry)
    habit_engine: HabitInferenceEngine | None = None
    class_manager: SemanticHabitClassManager | None = None
    cor_subsystem: CORSubsystem | None = None
    ssu: SymbolicScreenUnderstanding | None = None
    cognitive_surface: CognitiveSurface | None = None
    log_path: Path = field(default_factory=lambda: Path(DEFAULT_LOG_PATH))

    def forget(
        self,
        request: IntentionalForgetRequest,
        *,
        authority: str = "operator",
    ) -> IntentionalForgetResult:
        timestamp = _now()
        cascade = request.forget_scope == "cascade"
        forget_tx_id = self._forget_tx_id(request, authority=authority)
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
        outcome = self._apply_forget(request, authority=authority)
        post_state_hash = self._state_hash()
        target_ref, redacted = _sanitize_target(request.target_type, request.target_id)
        append_json(
            self.log_path,
            {
                "event": "intentional_forget",
                "target_type": request.target_type,
                "target": target_ref,
                "cascade": cascade,
                "authority": authority,
                "proof_level": request.proof_level,
                "forget_tx_id": forget_tx_id,
                "post_state_hash": post_state_hash,
                "redacted_target": redacted,
            },
        )
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
        if error_reason:
            blocked = [{"target": request.target_type, "reason": error_reason}]
        if replay_status == "already_applied":
            blocked = list(blocked) + [{"target": "forget_tx_id", "reason": "already_applied"}]

        payload = {
            "view": "intentional_forget_diff",
            "schema_version": "forget_diff_v1",
            "request": {
                "target_type": request.target_type,
                "target_id": request.target_id,
                "forget_scope": request.forget_scope,
                "proof_level": request.proof_level,
                "authority": authority,
            },
            "forget_tx_id": forget_tx_id,
            "replay_status": replay_status,
            "primary_targets": _sorted_unique(outcome.primary),
            "cascaded_removals": _sorted_unique(outcome.cascaded),
            "removals": _sorted_unique(outcome.removals),
            "authority_deltas": tuple(authority_diff.get("changes", ())),
            "blocked": _sorted_blockers(blocked),
            "skipped": _sorted_blockers(outcome.skipped),
            "narrative_summary_hashes": _sorted_hashes(narrative_summary_hashes),
            "state_hashes": {"before": pre_state_hash, "after": post_state_hash},
        }
        diff_hash = _hash_payload(payload)
        return ForgetDiff(
            request=payload["request"],
            forget_tx_id=forget_tx_id,
            replay_status=replay_status,
            primary_targets=tuple(payload["primary_targets"]),
            cascaded_removals=tuple(payload["cascaded_removals"]),
            removals=tuple(payload["removals"]),
            authority_deltas=tuple(payload["authority_deltas"]),
            blocked=tuple(payload["blocked"]),
            skipped=tuple(payload["skipped"]),
            narrative_summary_hashes=tuple(payload["narrative_summary_hashes"]),
            state_hashes=payload["state_hashes"],
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
        )

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


def read_forget_log(path: Path | str = DEFAULT_LOG_PATH) -> list[dict[str, object]]:
    target = Path(path)
    if not target.exists():
        return []
    try:
        return read_json(target)
    except Exception:
        return []


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
        "schema_version": "forget_tx_v1",
    }
    return _hash_payload(payload)


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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "ForgetDiff",
    "IntentionalForgetRequest",
    "IntentionalForgetResult",
    "IntentionalForgettingService",
    "DEFAULT_LOG_PATH",
    "read_forget_log",
]
