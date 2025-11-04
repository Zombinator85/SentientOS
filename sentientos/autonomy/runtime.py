"""Co-ordinates the hardened SentientOS autonomy subsystems."""

from __future__ import annotations

import json
import logging
import math
import time
from collections import deque
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
import json
import os
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Callable, Dict, List, Mapping, MutableMapping, Optional, Sequence

from curiosity_goal_helper import CuriosityConfig as HelperCuriosityConfig
from curiosity_goal_helper import CuriosityGoalHelper, configure_global_helper
from curiosity_executor import CuriosityExecutor
from sentientos.actuators.gui_control import GUIController
from sentientos.actuators.tts_speaker import TTSSpeaker
from sentientos.agents.browser_automator import BrowserAutomator
from sentientos.daemons.curiosity_loop import CuriosityLoopDaemon
from sentientos.perception.asr_listener import ASRListener
from sentientos.perception.screen_ocr import ScreenOCR
from ..config import (
    CriticConfig,
    GoalsBudgetConfig,
    GoalsCuratorConfig,
    HungryEyesActiveLearningConfig,
    MemoryCuratorConfig,
    OracleBudgetConfig,
    OracleConfig,
    ReflexionBudgetConfig,
    ReflexionConfig,
    RuntimeConfig,
)
from ..daemons.hungry_eyes import HungryEyesDatasetBuilder, HungryEyesSentinel
from ..determinism import seed_everything
from ..metrics import MetricsRegistry
from ..privacy import PrivacyManager
from .audit import AutonomyActionLogger
from .state import MoodStateManager
from .conversation_triggers import ConversationTriggers

LOGGER = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SlidingWindowLimiter:
    """Simple sliding window rate limiter used for safety budgets."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = max(0, int(limit))
        self._window = float(window_seconds)
        self._events: deque[float] = deque()

    @property
    def limit(self) -> int:
        return self._limit

    def _prune(self, now: float) -> None:
        cutoff = now - self._window
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()

    def consume(self, *, now: Optional[float] = None) -> bool:
        if self._limit <= 0:
            return True
        instant = time.time() if now is None else float(now)
        self._prune(instant)
        if len(self._events) >= self._limit:
            return False
        self._events.append(instant)
        return True

    def remaining(self, *, now: Optional[float] = None) -> Optional[int]:
        if self._limit <= 0:
            return None
        instant = time.time() if now is None else float(now)
        self._prune(instant)
        return max(self._limit - len(self._events), 0)


class OracleMode(str, Enum):
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class CouncilOutcome(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    TIED = "tied"


@dataclass
class CouncilDecision:
    outcome: CouncilOutcome
    votes_for: int
    votes_against: int
    quorum_met: bool
    notes: str = ""


@dataclass
class AutonomyStatus:
    modules: Dict[str, Mapping[str, object]] = field(default_factory=dict)

    @property
    def healthy(self) -> bool:
        return all(
            module.get("status") in {"healthy", "disabled"}
            for module in self.modules.values()
        )

    def overall_state(self) -> str:
        return "healthy" if self.healthy else "degraded"


class MemoryCurator:
    def __init__(
        self,
        config: MemoryCuratorConfig,
        metrics: MetricsRegistry,
        privacy: PrivacyManager | None = None,
    ) -> None:
        self._config = config
        self._metrics = metrics
        self._lock = Lock()
        self._sessions: MutableMapping[str, List[dict]] = {}
        self._capsules: MutableMapping[str, List[dict]] = {}
        self._privacy = privacy
        self._importance_floor = float(config.forgetting_curve.min_keep_score)
        self._target_capsules = max(1, int(config.target_capsules))

    def ingest_turn(self, session_id: str, turn: Mapping[str, object], *, importance: float, corr_id: str) -> None:
        if not self._config.enable:
            return
        enriched = dict(turn)
        enriched["importance"] = float(importance)
        enriched.setdefault("timestamp", time.monotonic())
        with self._lock:
            self._sessions.setdefault(session_id, []).append(enriched)
        LOGGER.info(
            json.dumps(
                {
                    "event": "memory_turn_ingested",
                    "session": session_id,
                    "corr_id": corr_id,
                    "importance": importance,
                }
            )
        )

    def rollup_session(self, session_id: str, corr_id: str) -> Optional[dict]:
        if not self._config.enable:
            return None
        with self._lock:
            turns = list(self._sessions.get(session_id, ()))
            if not turns:
                return None
            summary = self._build_capsule(turns)
            if self._privacy:
                summary = self._privacy.hash_capsule(summary)
            capsule_log = self._capsules.setdefault(session_id, [])
            capsule_log.append(summary)
            self._sessions[session_id] = self._apply_forgetting(turns)
        self._metrics.increment("sos_curator_capsules_written_total")
        capsule_count = sum(len(v) for v in self._capsules.values())
        if self._target_capsules:
            pressure = capsule_count / float(self._target_capsules)
            self._metrics.set_gauge("sos_memory_target_pressure", pressure)
            self._auto_calibrate(pressure)
        LOGGER.info(
            json.dumps(
                {
                    "event": "memory_capsule_written",
                    "session": session_id,
                    "corr_id": corr_id,
                    "turns": len(turns),
                    "importance": summary["importance"],
                }
            )
        )
        return summary

    def backlog(self) -> int:
        with self._lock:
            return sum(len(turns) for turns in self._sessions.values())

    def _build_capsule(self, turns: Sequence[Mapping[str, object]]) -> dict:
        importance = sum(float(turn.get("importance", 0.0)) for turn in turns)
        importance = min(importance, float(self._config.max_capsule_len))
        summary_texts = [str(turn.get("text", "")) for turn in turns]
        summary = {
            "text": " \n".join(summary_texts)[: self._config.max_capsule_len],
            "importance": importance,
            "turn_count": len(turns),
            "created_at": _utcnow().isoformat(),
        }
        return summary

    def _apply_forgetting(self, turns: Sequence[Mapping[str, object]]) -> List[dict]:
        horizon = self._config.forgetting_curve.half_life_days
        keep_score = self._importance_floor
        now = time.monotonic()
        retained: List[dict] = []
        for turn in turns:
            importance = float(turn.get("importance", 0.0))
            ts = float(turn.get("timestamp", now))
            age_days = max(0.0, (now - ts) / (60 * 60 * 24))
            decay = math.exp(-math.log(2) * age_days / max(horizon, 1e-6))
            if importance * decay >= keep_score:
                retained.append(dict(turn))
        return retained

    def _auto_calibrate(self, pressure: float) -> None:
        if not self._config.auto_calibrate_importance:
            return
        if pressure > 1.2:
            self._importance_floor = min(1.0, self._importance_floor * 1.05)
        elif pressure < 0.8:
            self._importance_floor = max(0.05, self._importance_floor * 0.95)

    def status(self) -> Mapping[str, object]:
        if not self._config.enable:
            return {"status": "disabled"}
        return {"status": "healthy", "backlog": self.backlog(), "capsules": sum(len(v) for v in self._capsules.values())}


class ReflexionEngine:
    def __init__(
        self,
        config: ReflexionConfig,
        metrics: MetricsRegistry,
        budget: ReflexionBudgetConfig,
    ) -> None:
        self._config = config
        self._metrics = metrics
        self._semaphore = BoundedSemaphore(value=4)
        self._notes: List[dict] = []
        self._budget = SlidingWindowLimiter(budget.max_per_hour, 3600.0)
        self._last_rate_limited: Optional[str] = None

    def run(self, task: str, *, corr_id: str, timeout_s: float = 5.0) -> Optional[dict]:
        if not self._config.enable:
            return None
        if not self._budget.consume():
            self._last_rate_limited = _utcnow().isoformat()
            self._metrics.increment("sos_reflexion_rate_limited_total")
            LOGGER.warning(
                "Reflexion rate-limited corr_id=%s limit=%s", corr_id, self._budget.limit
            )
            return None
        start = time.monotonic()
        acquired = self._semaphore.acquire(timeout=timeout_s)
        if not acquired:
            LOGGER.warning("Reflexion semaphore saturated for corr_id=%s", corr_id)
            return None
        try:
            elapsed = time.monotonic() - start
            note = {
                "task": task[: self._config.max_tokens],
                "corr_id": corr_id,
                "elapsed_ms": elapsed * 1000,
                "ts": _utcnow().isoformat(),
            }
            self._notes.append(note)
            self._metrics.increment("sos_reflexion_notes_total")
            self._metrics.observe("sos_reflexion_latency_ms", elapsed * 1000)
            if self._config.store_path:
                self._persist(note)
            return note
        finally:
            self._semaphore.release()

    def _persist(self, note: Mapping[str, object]) -> None:
        path = Path(self._config.store_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(note) + "\n")

    def status(self) -> Mapping[str, object]:
        if not self._config.enable:
            return {"status": "disabled"}
        remaining = self._budget.remaining()
        status = {
            "status": "healthy",
            "notes": len(self._notes),
        }
        if self._budget.limit > 0:
            status["budget_limit"] = self._budget.limit
            status["budget_remaining"] = remaining
            if remaining == 0:
                status["status"] = "limited"
            if self._last_rate_limited:
                status["last_rate_limited"] = self._last_rate_limited
        return status


class CriticEngine:
    def __init__(self, config: CriticConfig, metrics: MetricsRegistry) -> None:
        self._config = config
        self._metrics = metrics
        self._disagreements: List[dict] = []
        self._semaphore = BoundedSemaphore(value=4)

    def review(
        self,
        payload: Mapping[str, object],
        *,
        corr_id: str,
        timeout_s: Optional[float] = None,
    ) -> Mapping[str, object]:
        limit = timeout_s or self._config.factcheck.timeout_s
        acquired = self._semaphore.acquire(timeout=limit)
        if not acquired:
            LOGGER.warning("Critic concurrency saturated corr_id=%s", corr_id)
            return {
                "corr_id": corr_id,
                "policy": self._config.policy,
                "disagreement": False,
                "timed_out": True,
                "ts": _utcnow().isoformat(),
            }
        start = time.monotonic()
        try:
            if self._config.factcheck.enable and limit:
                time.sleep(min(limit, 0.01))
            disagreement = bool(payload.get("disagreement"))
            result = {
                "corr_id": corr_id,
                "policy": self._config.policy,
                "disagreement": disagreement,
                "timed_out": False,
                "ts": _utcnow().isoformat(),
            }
            if disagreement:
                self._disagreements.append(result)
                self._metrics.increment("sos_critic_disagreements_total")
            self._metrics.observe("sos_critic_latency_ms", (time.monotonic() - start) * 1000)
            return result
        finally:
            self._semaphore.release()

    def disagreements(self) -> List[dict]:
        return list(self._disagreements)

    def status(self) -> Mapping[str, object]:
        return {
            "status": "healthy",
            "disagreements": len(self._disagreements),
            "policy": self._config.policy,
        }


class Council:
    def __init__(self, metrics: MetricsRegistry, members: Sequence[str], quorum: int, tie_breaker: str) -> None:
        self._metrics = metrics
        self._members = list(members)
        self._quorum = max(1, quorum)
        self._tie_breaker = tie_breaker
        self._history: deque[dict] = deque(maxlen=200)

    def vote(self, proposal: str, *, corr_id: str, votes_for: int, votes_against: int) -> CouncilDecision:
        start = time.monotonic()
        quorum_met = (votes_for + votes_against) >= self._quorum
        if votes_for > votes_against:
            outcome = CouncilOutcome.APPROVED
        elif votes_against > votes_for:
            outcome = CouncilOutcome.REJECTED
        else:
            outcome = CouncilOutcome.TIED
        notes = ""
        if outcome == CouncilOutcome.TIED:
            breaker = self._tie_breaker.lower().strip()
            if breaker in {"approve", "chair", "oracle"}:
                outcome = CouncilOutcome.APPROVED
                notes = f"tie_breaker:{self._tie_breaker}"
            else:
                outcome = CouncilOutcome.REJECTED
                notes = f"tie_breaker:{self._tie_breaker or 'default-reject'}"
        if not quorum_met:
            self._metrics.increment("sos_council_quorum_misses_total")
        self._metrics.increment(
            "sos_council_votes_total",
            labels={"result": outcome.value},
        )
        elapsed_ms = (time.monotonic() - start) * 1000
        self._metrics.observe("sos_council_vote_latency_ms", elapsed_ms)
        note = {
            "event": "council_vote",
            "proposal": proposal,
            "corr_id": corr_id,
            "votes_for": votes_for,
            "votes_against": votes_against,
            "quorum_met": quorum_met,
            "ts": _utcnow().isoformat(),
        }
        if notes:
            note["notes"] = notes
        LOGGER.info(json.dumps(note))
        self._history.append(
            {
                "proposal": proposal,
                "outcome": outcome.value,
                "votes_for": votes_for,
                "votes_against": votes_against,
                "quorum_met": quorum_met,
                "ts": note["ts"],
            }
        )
        return CouncilDecision(
            outcome=outcome,
            votes_for=votes_for,
            votes_against=votes_against,
            quorum_met=quorum_met,
            notes=notes,
        )

    def status(self) -> Mapping[str, object]:
        return {
            "status": "healthy",
            "members": list(self._members),
            "quorum": self._quorum,
        }

    def history(self, limit: int = 20) -> List[dict]:
        limit = max(int(limit), 1)
        return list(self._history)[-limit:]


class OracleGateway:
    def __init__(
        self,
        config: OracleConfig,
        metrics: MetricsRegistry,
        budget: OracleBudgetConfig,
    ) -> None:
        self._config = config
        self._metrics = metrics
        self._mode = OracleMode.OFFLINE
        self._budget = SlidingWindowLimiter(budget.max_requests_per_day, 86400.0)
        self._last_rate_limited: Optional[str] = None
        self._last_degraded: Optional[str] = None

    @property
    def mode(self) -> OracleMode:
        return self._mode

    def execute(self, fn: Callable[[], object], *, corr_id: str) -> Mapping[str, object]:
        if not self._config.enable:
            self._mode = OracleMode.OFFLINE
            return {"mode": self._mode.value, "result": None}
        if not self._budget.consume():
            self._mode = OracleMode.DEGRADED
            self._last_rate_limited = _utcnow().isoformat()
            self._last_degraded = self._last_rate_limited
            self._metrics.increment("sos_oracle_rate_limited_total")
            LOGGER.warning(
                "Oracle rate-limited corr_id=%s limit=%s", corr_id, self._budget.limit
            )
            return {
                "mode": self._mode.value,
                "result": None,
                "error": "rate_limited",
            }
        attempt = 0
        delay = 0.1
        last_error: Optional[str] = None
        start = time.monotonic()
        while attempt < 3:
            attempt += 1
            try:
                result = _call_with_timeout(fn, timeout=self._config.timeout_s)
            except Exception as exc:  # pragma: no cover - exercised via tests
                last_error = str(exc)
                time.sleep(delay)
                delay *= 2
                continue
            else:
                self._mode = OracleMode.ONLINE
                elapsed = (time.monotonic() - start) * 1000
                self._metrics.increment("sos_oracle_requests_total", labels={"mode": self._mode.value})
                self._metrics.observe("sos_oracle_latency_ms", elapsed)
                self._last_degraded = None
                return {"mode": self._mode.value, "result": result, "elapsed_ms": elapsed}
        self._mode = OracleMode.DEGRADED
        elapsed = (time.monotonic() - start) * 1000
        self._metrics.increment("sos_oracle_requests_total", labels={"mode": self._mode.value})
        self._metrics.observe("sos_oracle_latency_ms", elapsed)
        LOGGER.warning(
            "Oracle degraded after retries corr_id=%s error=%s", corr_id, last_error
        )
        self._last_degraded = _utcnow().isoformat()
        return {"mode": self._mode.value, "result": None, "error": last_error}

    def status(self) -> Mapping[str, object]:
        if not self._config.enable:
            return {"status": "disabled"}
        remaining = self._budget.remaining()
        status = {
            "status": "healthy" if self._mode == OracleMode.ONLINE else "degraded",
            "mode": self._mode.value,
        }
        if self._budget.limit > 0:
            status["budget_limit"] = self._budget.limit
            status["budget_remaining"] = remaining
            if self._last_rate_limited:
                status["last_rate_limited"] = self._last_rate_limited
        if self._last_degraded:
            status["last_degraded_at"] = self._last_degraded
        return status


class GoalCurator:
    def __init__(
        self,
        config: GoalsCuratorConfig,
        metrics: MetricsRegistry,
        budget: GoalsBudgetConfig,
    ) -> None:
        self._config = config
        self._metrics = metrics
        self._active: List[dict] = []
        self._last_created: Optional[float] = None
        self._tokens: float = float(config.max_concurrent_auto_goals)
        self._last_refill = time.monotonic()
        self._budget = SlidingWindowLimiter(budget.max_autocreated_per_day, 86400.0)
        self._last_rate_limited: Optional[str] = None

    def consider(self, proposal: Mapping[str, object], *, corr_id: str, support_count: int, now: Optional[float] = None) -> bool:
        if not self._config.enable:
            return False
        now = time.monotonic() if now is None else now
        self._refill(now)
        if not self._budget.consume(now=time.time()):
            self._last_rate_limited = _utcnow().isoformat()
            self._metrics.increment("sos_goals_rate_limited_total")
            LOGGER.warning("Goal curator rate-limited corr_id=%s", corr_id)
            return False
        if support_count < self._config.min_support_count:
            return False
        if self._tokens < 1:
            return False
        if self._last_created is not None:
            min_gap = self._config.min_days_between_auto_goals * 86400
            if now - self._last_created < min_gap:
                return False
        if len(self._active) >= self._config.max_concurrent_auto_goals:
            return False
        goal = dict(proposal)
        goal["corr_id"] = corr_id
        goal["ts"] = _utcnow().isoformat()
        self._active.append(goal)
        self._tokens -= 1
        self._last_created = now
        self._metrics.increment("sos_goals_autocreated_total")
        return True

    def _refill(self, now: float) -> None:
        max_tokens = max(self._config.max_concurrent_auto_goals, 1)
        window_seconds = max(self._config.min_days_between_auto_goals * 86400.0, 1.0)
        rate = max_tokens / window_seconds
        delta = now - self._last_refill
        self._tokens = min(float(max_tokens), self._tokens + delta * rate)
        self._last_refill = now

    def status(self) -> Mapping[str, object]:
        if not self._config.enable:
            return {"status": "disabled"}
        status = {
            "status": "healthy",
            "active": len(self._active),
            "tokens": round(self._tokens, 3),
        }
        remaining = self._budget.remaining()
        if self._budget.limit > 0:
            status["budget_limit"] = self._budget.limit
            status["budget_remaining"] = remaining
            if remaining == 0:
                status["status"] = "limited"
            if self._last_rate_limited:
                status["last_rate_limited"] = self._last_rate_limited
        return status


class HungryEyesActiveLearner:
    def __init__(self, config: HungryEyesActiveLearningConfig, metrics: MetricsRegistry) -> None:
        self._config = config
        self._metrics = metrics
        self._sentinel = HungryEyesSentinel()
        self._pending: List[Mapping[str, object]] = []
        self._corpus: List[Mapping[str, object]] = []
        self._last_retrain: Optional[str] = None
        if config.seed is not None:
            seed_everything(override=config.seed)
        if not config.enable:
            self._metrics.set_gauge("sos_hungryeyes_corpus_bytes", 0.0)

    def observe(self, event: Mapping[str, object]) -> Mapping[str, object]:
        if not self._config.enable:
            return {"retrain": False, "risk": 0.0}
        self._corpus.append(event)
        self._pending.append(event)
        self._cap_corpus()
        retrained = False
        if len(self._pending) >= self._config.retrain_every_n_events:
            dataset_builder = HungryEyesDatasetBuilder()
            dataset_builder.add_many(self._corpus)
            self._sentinel.fit(dataset_builder.build())
            self._pending.clear()
            self._last_retrain = _utcnow().isoformat()
            self._metrics.increment("sos_hungryeyes_retrains_total")
            retrained = True
        risk_report = self._sentinel.observe(event)
        self._metrics.set_gauge("sos_hungryeyes_corpus_bytes", self._estimate_corpus_bytes())
        return {
            "retrain": retrained,
            "risk": risk_report.get("risk", 0.0),
            "last_retrain": self._last_retrain,
        }

    def _estimate_corpus_bytes(self) -> float:
        return float(sum(len(json.dumps(item)) for item in self._corpus))

    def _cap_corpus(self) -> None:
        max_bytes = self._config.max_corpus_mb * 1024 * 1024
        while self._estimate_corpus_bytes() > max_bytes and self._corpus:
            self._corpus.pop(0)

    def status(self) -> Mapping[str, object]:
        if not self._config.enable:
            return {"status": "disabled"}
        return {
            "status": "healthy",
            "corpus_size": len(self._corpus),
            "last_retrain": self._last_retrain,
        }


class AutonomyRuntime:
    def __init__(self, config: RuntimeConfig, *, metrics: Optional[MetricsRegistry] = None) -> None:
        self.config = config
        self.metrics = metrics or MetricsRegistry()
        self.privacy = PrivacyManager(config.privacy)
        self.audit_log = AutonomyActionLogger()
        state_dir = Path("glow/state")
        state_dir.mkdir(parents=True, exist_ok=True)
        self._panic_path = state_dir / "panic.json"
        self._panic = self._load_panic_state()
        self.mood_state = MoodStateManager(
            state_dir / "mood.json",
            restore=config.persistence.restore_mood,
            decay_factor=config.persistence.decay_factor,
        )
        snapshot = self.mood_state.load(config.tts.personality.baseline_mood)
        panic_flag = lambda: self._panic
        mood_provider = lambda: self.mood_state.current_mood() or snapshot.mood
        self.asr = ASRListener(config.audio, metrics=self.metrics)
        self.tts = TTSSpeaker(config.tts, metrics=self.metrics, mood_provider=mood_provider)
        self.screen = ScreenOCR(config.screen, metrics=self.metrics)
        self.gui = GUIController(
            config.gui,
            panic_flag=panic_flag,
            audit_logger=self.audit_log,
        )
        self.social = BrowserAutomator(
            config.social,
            metrics=self.metrics,
            panic_flag=panic_flag,
            audit_logger=self.audit_log,
            council_prompt=self._request_council_confirmation,
        )
        self.conversation = ConversationTriggers(config.conversation, metrics=self.metrics)
        self.memory_curator = MemoryCurator(config.memory.curator, self.metrics, self.privacy)
        self.reflexion = ReflexionEngine(
            config.reflexion,
            self.metrics,
            config.budgets.reflexion,
        )
        self.critic = CriticEngine(config.critic, self.metrics)
        self.council = Council(
            self.metrics,
            members=config.council.members,
            quorum=config.council.quorum,
            tie_breaker=config.council.tie_breaker,
        )
        self.oracle = OracleGateway(
            config.oracle,
            self.metrics,
            config.budgets.oracle,
        )
        self.goal_curator = GoalCurator(
            config.goals.curator,
            self.metrics,
            config.budgets.goals,
        )
        self.hungry_eyes = HungryEyesActiveLearner(config.hungry_eyes.active_learning, self.metrics)
        curiosity_cfg = HelperCuriosityConfig(
            enable=config.curiosity.enable,
            max_goals_per_hour=config.curiosity.max_goals_per_hour,
            cooldown_minutes=config.curiosity.cooldown_minutes,
            novelty_threshold=config.curiosity.novelty_threshold,
        )
        self.curiosity_helper = CuriosityGoalHelper(curiosity_cfg, metrics=self.metrics)
        configure_global_helper(self.curiosity_helper)
        self.curiosity_executor = CuriosityExecutor(
            self.curiosity_helper,
            metrics=self.metrics,
            critic=self.critic,
        )
        cadence = max(float(config.curiosity.cooldown_minutes) * 60.0, 60.0)
        self.curiosity = CuriosityLoopDaemon(
            self.curiosity_helper,
            self.curiosity_executor,
            cadence_seconds=cadence,
            metrics=self.metrics,
        )

    @classmethod
    def from_config(cls, config: Optional[RuntimeConfig] = None) -> "AutonomyRuntime":
        from ..config import load_runtime_config

        runtime_config = config or load_runtime_config()
        seed_everything(runtime_config)
        return cls(runtime_config)

    def status(self) -> AutonomyStatus:
        modules = {
            "ears": self.asr.status(),
            "voice": self.tts.status(),
            "screen": self.screen.status(),
            "gui": self.gui.status(),
            "social": self.social.status(),
            "conversation": self.conversation.status(),
            "memory_curator": self.memory_curator.status(),
            "reflexion": self.reflexion.status(),
            "critic": self.critic.status(),
            "council": self.council.status(),
            "oracle": self.oracle.status(),
            "goal_curator": self.goal_curator.status(),
            "hungry_eyes": self.hungry_eyes.status(),
            "curiosity": self.curiosity.status(),
        }
        return AutonomyStatus(modules=modules)

    def export_metrics(self) -> str:
        return self.metrics.export_prometheus()

    def persist_metrics(self) -> None:
        self.metrics.persist_prometheus()

    def activate_panic(self) -> None:
        self._panic = True
        self._write_panic_state(True)
        self.audit_log.log("system", "panic", "activated")

    def clear_panic(self) -> None:
        self._panic = False
        self._write_panic_state(False)
        self.audit_log.log("system", "panic", "cleared")

    def panic_active(self) -> bool:
        return self._panic

    def save_state(self) -> None:
        self.mood_state.save()

    def reset_mood_state(self) -> None:
        self.mood_state.reset()

    def _load_panic_state(self) -> bool:
        if not self._panic_path.exists():
            return False
        try:
            payload = json.loads(self._panic_path.read_text(encoding="utf-8"))
            return bool(payload.get("active", False))
        except Exception:
            return False

    def _write_panic_state(self, active: bool) -> None:
        payload = {"active": active, "timestamp": _utcnow().isoformat()}
        self._panic_path.write_text(json.dumps(payload), encoding="utf-8")
        if not active:
            self._panic_path.unlink(missing_ok=True)

    def _request_council_confirmation(self, action: str, target: str) -> bool:
        auto = os.getenv("SENTIENTOS_COUNCIL_AUTO_APPROVE", "0").lower()
        if auto in {"1", "true", "yes", "on"}:
            self.audit_log.log("council", "vote", "approved", action=action, target=target)
            return True
        LOGGER.warning("Council veto for %s on %s (auto-fail)", action, target)
        self.audit_log.log(
            "council",
            "vote",
            "blocked",
            action=action,
            target=target,
            reason="council_veto",
        )
        return False


def _call_with_timeout(fn: Callable[[], object], *, timeout: float) -> object:
    start = time.monotonic()
    result = fn()
    if (time.monotonic() - start) > timeout:
        raise TimeoutError("operation exceeded timeout")
    return result


__all__ = [
    "AutonomyRuntime",
    "AutonomyStatus",
    "CouncilDecision",
    "CouncilOutcome",
    "OracleMode",
]
