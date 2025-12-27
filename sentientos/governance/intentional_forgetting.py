from __future__ import annotations

import hashlib
import json
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
    cascade: bool
    post_state_hash: str
    impacted: tuple[str, ...] = ()
    redacted_target: bool = False


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
        impacted: list[str] = []
        if request.target_type == "all":
            impacted.extend(self._forget_all(cascade=cascade, authority=authority))
        elif request.target_type == "routine":
            impacted.extend(self._forget_routine(request.target_id, cascade=cascade, authority=authority))
        elif request.target_type == "habit":
            impacted.extend(self._forget_habit(request.target_id, cascade=cascade, authority=authority))
        elif request.target_type == "class":
            impacted.extend(self._forget_class(request.target_id, cascade=cascade, authority=authority))
        elif request.target_type == "cognitive":
            impacted.extend(self._forget_cognitive(request.target_id, authority=authority))
        elif request.target_type == "cor":
            impacted.extend(self._forget_cor(request.target_id, authority=authority))
        elif request.target_type == "ssu":
            impacted.extend(self._forget_ssu(request.target_id, authority=authority))
        else:
            raise ValueError(f"Unsupported forget target: {request.target_type}")

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
            cascade=cascade,
            post_state_hash=post_state_hash,
            impacted=tuple(impacted),
            redacted_target=redacted,
        )

    def _forget_routine(self, routine_id: str, *, cascade: bool, authority: str) -> list[str]:
        impacted = []
        if self.routine_registry.forget_routine(routine_id, forgotten_by=authority, reason="intentional_forget"):
            impacted.append(f"routine:{routine_id}")
        if cascade and self.class_manager is not None:
            for semantic_class in self.class_manager.list_classes():
                if routine_id in semantic_class.routine_ids:
                    self.class_manager.remove_member(
                        semantic_class.name,
                        routine_id=routine_id,
                        removed_by=authority,
                        reason="routine_forgotten",
                    )
                    impacted.append(f"semantic_class_member:{semantic_class.name}:{routine_id}")
        if cascade and self.habit_engine is not None:
            habit_id = _habit_id_from_routine(routine_id)
            if habit_id:
                if self.habit_engine.forget_habit(habit_id, forgotten_by=authority, reason="routine_forgotten"):
                    impacted.append(f"habit:{habit_id}")
        return impacted

    def _forget_habit(self, habit_id: str, *, cascade: bool, authority: str) -> list[str]:
        impacted = []
        if self.habit_engine is None:
            raise ValueError("Habit inference engine is required to forget habits")
        if self.habit_engine.forget_habit(habit_id, forgotten_by=authority, reason="intentional_forget"):
            impacted.append(f"habit:{habit_id}")
        if cascade:
            routine_id = f"routine-{habit_id}"
            if self.routine_registry.forget_routine(routine_id, forgotten_by=authority, reason="habit_forgotten"):
                impacted.append(f"routine:{routine_id}")
        return impacted

    def _forget_class(self, class_ref: str, *, cascade: bool, authority: str) -> list[str]:
        impacted = []
        if self.class_manager is None:
            raise ValueError("Semantic habit class manager is required to forget classes")
        semantic_class = self._resolve_class(class_ref)
        if semantic_class is None:
            self.class_manager.forget_class(class_ref, forgotten_by=authority, reason="intentional_forget")
            return impacted
        self.class_manager.forget_class(semantic_class.name, forgotten_by=authority, reason="intentional_forget")
        impacted.append(f"class:{semantic_class.name}")
        if cascade:
            for routine_id in semantic_class.routine_ids:
                if self.routine_registry.forget_routine(
                    routine_id,
                    forgotten_by=authority,
                    reason="semantic_class_forgotten",
                ):
                    impacted.append(f"routine:{routine_id}")
                if self.habit_engine is not None:
                    habit_id = _habit_id_from_routine(routine_id)
                    if habit_id and self.habit_engine.forget_habit(
                        habit_id,
                        forgotten_by=authority,
                        reason="semantic_class_forgotten",
                    ):
                        impacted.append(f"habit:{habit_id}")
        return impacted

    def _forget_cognitive(self, target_id: str, *, authority: str) -> list[str]:
        if self.cognitive_surface is None:
            raise ValueError("Cognitive surface is required to forget cognitive artifacts")
        if target_id in {"*", "all"}:
            removed = self.cognitive_surface.forget_all_preferences(
                forgotten_by=authority,
                reason="intentional_forget",
            )
            return [f"cognitive:{key}" for key in removed]
        removed = self.cognitive_surface.forget_preferences(
            [target_id],
            forgotten_by=authority,
            reason="intentional_forget",
        )
        return [f"cognitive:{key}" for key in removed]

    def _forget_cor(self, hypothesis: str, *, authority: str) -> list[str]:
        if self.cor_subsystem is None:
            raise ValueError("COR subsystem is required to forget hypotheses")
        if self.cor_subsystem.forget_hypothesis(hypothesis, reason="intentional_forget"):
            return [f"cor:{_hash_reference(hypothesis)}"]
        return []

    def _forget_ssu(self, target_id: str, *, authority: str) -> list[str]:
        if self.ssu is None:
            raise ValueError("SSU subsystem is required to forget symbols")
        key = self.ssu.parse_symbol_key(target_id)
        if self.ssu.forget_symbol_key(key):
            return [f"ssu:{self.ssu.serialize_symbol_key(key)}"]
        return []

    def _forget_all(self, *, cascade: bool, authority: str) -> list[str]:
        impacted = []
        routine_ids = self.routine_registry.forget_all(forgotten_by=authority, reason="intentional_forget")
        impacted.extend([f"routine:{rid}" for rid in routine_ids])
        if self.habit_engine is not None:
            for habit in self.habit_engine.list_habits():
                self.habit_engine.forget_habit(
                    habit.habit_id,
                    forgotten_by=authority,
                    reason="intentional_forget_all",
                )
                impacted.append(f"habit:{habit.habit_id}")
        if self.class_manager is not None:
            for semantic_class in self.class_manager.list_classes():
                self.class_manager.forget_class(
                    semantic_class.name,
                    forgotten_by=authority,
                    reason="intentional_forget_all",
                )
                impacted.append(f"class:{semantic_class.name}")
        if self.cor_subsystem is not None:
            for hypothesis in self.cor_subsystem.list_hypotheses():
                self.cor_subsystem.forget_hypothesis(hypothesis, reason="intentional_forget_all")
                impacted.append(f"cor:{_hash_reference(hypothesis)}")
        if self.ssu is not None:
            for key in self.ssu.list_forgotten():
                impacted.append(f"ssu:{self.ssu.serialize_symbol_key(key)}")
            for key in self.ssu.list_symbol_records():
                if self.ssu.forget_symbol_key(key):
                    impacted.append(f"ssu:{self.ssu.serialize_symbol_key(key)}")
        if self.cognitive_surface is not None:
            removed = self.cognitive_surface.forget_all_preferences(
                forgotten_by=authority,
                reason="intentional_forget_all",
            )
            impacted.extend([f"cognitive:{key}" for key in removed])
        if cascade and self.class_manager is not None:
            for semantic_class in self.class_manager.list_classes():
                for routine_id in semantic_class.routine_ids:
                    if self.routine_registry.forget_routine(
                        routine_id,
                        forgotten_by=authority,
                        reason="intentional_forget_all",
                    ):
                        impacted.append(f"routine:{routine_id}")
        return impacted

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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "IntentionalForgetRequest",
    "IntentionalForgetResult",
    "IntentionalForgettingService",
    "DEFAULT_LOG_PATH",
    "read_forget_log",
]
