"""Helpers for creating and tracking curiosity-driven goals.

The helper centralises rate limiting, queue management, and observability for
curiosity tasks so multiple modules (``perception_reasoner`` as the primary
producer and the curiosity executor/daemon as consumers) share a consistent
view of the backlog.  The implementation intentionally favours lightweight
heuristics over heavyweight coordination primitives so it can run in unit
tests and rehearsal environments without extra services.
"""

from __future__ import annotations

import dataclasses
import threading
import time
from collections import deque
from typing import Deque, Dict, Iterable, List, Mapping, MutableMapping, Optional

import memory_manager as mm
from sentientos.metrics import MetricsRegistry


@dataclasses.dataclass
class CuriosityConfig:
    """Runtime configuration controlling curiosity goal creation."""

    enable: bool = True
    max_goals_per_hour: int = 10
    cooldown_minutes: int = 6
    novelty_threshold: float = 0.45


class _SlidingWindowBudget:
    """Simple per-source counter enforcing a maximum over a sliding window."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = max(0, int(limit))
        self._window = float(window_seconds)
        self._events: Deque[float] = deque()

    def allow(self, *, now: Optional[float] = None) -> bool:
        if self._limit <= 0:
            return True
        instant = time.time() if now is None else float(now)
        cutoff = instant - self._window
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()
        if len(self._events) >= self._limit:
            return False
        self._events.append(instant)
        return True

    def remaining(self, *, now: Optional[float] = None) -> Optional[int]:
        if self._limit <= 0:
            return None
        instant = time.time() if now is None else float(now)
        cutoff = instant - self._window
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()
        return max(self._limit - len(self._events), 0)


class CuriosityGoalHelper:
    """Create curiosity tasks from perception summaries with rate limiting."""

    def __init__(
        self,
        config: CuriosityConfig | None = None,
        *,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._config = config or CuriosityConfig()
        self._metrics = metrics
        self._lock = threading.RLock()
        self._queue: Deque[dict] = deque()
        self._inflight: MutableMapping[str, dict] = {}
        self._recent_novelty: Deque[tuple[float, float]] = deque(maxlen=32)
        self._recent_results: Deque[Mapping[str, object]] = deque(maxlen=10)
        window_seconds = max(3600.0, self._config.cooldown_minutes * 60.0)
        self._budget = _SlidingWindowBudget(
            self._config.max_goals_per_hour, window_seconds
        )
        self._cooldown_until: float | None = None

    @property
    def config(self) -> CuriosityConfig:
        return self._config

    def reconfigure(self, config: CuriosityConfig) -> None:
        with self._lock:
            self._config = config
            window_seconds = max(3600.0, config.cooldown_minutes * 60.0)
            self._budget = _SlidingWindowBudget(config.max_goals_per_hour, window_seconds)

    def create_goal(
        self,
        observation: Mapping[str, object],
        *,
        novelty: float,
        source: str,
    ) -> Optional[dict]:
        """Queue a curiosity investigation when the observation warrants it."""

        if not self._config.enable:
            return None
        summary = str(observation.get("summary") or "").strip()
        if not summary:
            return None
        novelty = float(novelty)
        novel_objects: Iterable[str] = observation.get("novel_objects") or []
        if isinstance(novel_objects, str):
            novel_objects = [novel_objects]
        novelty_trigger = novelty >= self._config.novelty_threshold or any(novel_objects)
        if not novelty_trigger:
            return None
        now = time.time()
        with self._lock:
            if self._cooldown_until and now < self._cooldown_until:
                return None
            if not self._budget.allow(now=now):
                self._cooldown_until = now + (self._config.cooldown_minutes * 60.0)
                if self._metrics is not None:
                    self._metrics.increment("curiosity_rate_limited_total")
                return None
            goal_text = self._compose_goal_text(summary, novel_objects)
            goal = mm.add_goal(
                goal_text,
                intent={
                    "type": "curiosity",
                    "observation": {
                        "id": observation.get("observation_id"),
                        "summary": summary,
                        "novel_objects": list(novel_objects),
                    },
                    "novelty": novelty,
                },
                user=source,
                priority=2,
            )
            entry = {
                "goal": goal,
                "observation": dict(observation),
                "created_at": time.time(),
                "source": source,
            }
            self._queue.append(entry)
            self._recent_novelty.append((now, novelty))
            if self._metrics is not None:
                self._metrics.increment("curiosity_goals_created_total")
                self._metrics.set_gauge("curiosity_queue_length", float(len(self._queue)))
        return goal

    def _compose_goal_text(self, summary: str, novel_objects: Iterable[str]) -> str:
        objects = [obj for obj in novel_objects if obj]
        if objects:
            focus = ", ".join(str(obj) for obj in objects)
            return f"Investigate curiosity cue: {focus}"
        return f"Investigate recent perception: {summary[:120]}"

    def pop_goal(self) -> Optional[dict]:
        with self._lock:
            if not self._queue:
                return None
            entry = self._queue.popleft()
            goal = entry["goal"]
            self._inflight[goal["id"]] = entry
            if self._metrics is not None:
                self._metrics.set_gauge("curiosity_queue_length", float(len(self._queue)))
            return entry

    def complete_goal(self, goal_id: str, result: Mapping[str, object]) -> None:
        with self._lock:
            self._inflight.pop(goal_id, None)
            if self._metrics is not None:
                self._metrics.increment("curiosity_goals_completed_total")
            self._recent_results.append(result)
            observation_id = result.get("observation_id")
            if observation_id:
                try:
                    mm.update_novelty_score(str(observation_id), -0.05)
                except Exception:
                    # Best-effort: novelty updates should not break execution.
                    pass

    def queue_length(self) -> int:
        with self._lock:
            return len(self._queue)

    def inflight(self) -> List[dict]:
        with self._lock:
            return list(self._inflight.values())

    def recent_novelty(self) -> List[tuple[float, float]]:
        with self._lock:
            return list(self._recent_novelty)

    def status(self) -> Mapping[str, object]:
        with self._lock:
            state = {
                "queue": len(self._queue),
                "inflight": len(self._inflight),
                "recent_novelty": [
                    {"ts": ts, "score": score} for ts, score in self._recent_novelty
                ][-5:],
                "recent_outcomes": list(self._recent_results),
            }
            if not self._config.enable:
                state["status"] = "paused"
                return state
            status = "idle"
            if self._queue or self._inflight:
                status = "active"
            remaining = self._budget.remaining()
            if remaining is not None:
                state["budget_remaining"] = remaining
                state["budget_limit"] = self._config.max_goals_per_hour
                if remaining == 0:
                    status = "cooldown"
            if self._cooldown_until and time.time() < self._cooldown_until:
                status = "cooldown"
                state["cooldown_until"] = self._cooldown_until
            state["status"] = status
            return state


_GLOBAL_HELPER: CuriosityGoalHelper | None = None
_GLOBAL_LOCK = threading.Lock()


def configure_global_helper(helper: CuriosityGoalHelper) -> None:
    with _GLOBAL_LOCK:
        global _GLOBAL_HELPER
        _GLOBAL_HELPER = helper


def get_global_helper() -> CuriosityGoalHelper:
    with _GLOBAL_LOCK:
        global _GLOBAL_HELPER
        if _GLOBAL_HELPER is None:
            _GLOBAL_HELPER = CuriosityGoalHelper()
        return _GLOBAL_HELPER


__all__ = [
    "CuriosityConfig",
    "CuriosityGoalHelper",
    "configure_global_helper",
    "get_global_helper",
]

