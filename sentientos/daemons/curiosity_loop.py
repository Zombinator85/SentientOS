from __future__ import annotations

import time
from typing import Mapping

import memory_manager as mm
from curiosity_executor import CuriosityExecutor
from curiosity_goal_helper import CuriosityGoalHelper
from sentientos.metrics import MetricsRegistry


class CuriosityLoopDaemon:
    """Periodic daemon wiring perception, curiosity, reflexion, and memory."""

    def __init__(
        self,
        helper: CuriosityGoalHelper,
        executor: CuriosityExecutor,
        *,
        cadence_seconds: float = 300.0,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._helper = helper
        self._executor = executor
        self._cadence = max(30.0, float(cadence_seconds))
        self._metrics = metrics
        self._last_run: float | None = None

    def run_once(self) -> list[Mapping[str, object]]:
        """Process queued curiosity goals and refresh insight digests."""

        processed = self._executor.drain()
        if processed and self._metrics is not None:
            self._metrics.increment("curiosity_loop_runs_total")
        self._last_run = time.time()
        if processed:
            mm.summarise_daily_insights()
        return processed

    def status(self) -> Mapping[str, object]:
        helper_status = self._helper.status()
        status = {
            "status": helper_status.get("status", "disabled"),
            "queue": helper_status.get("queue", 0),
            "recent_novelty": helper_status.get("recent_novelty", []),
            "inflight": helper_status.get("inflight", 0),
            "recent_outcomes": helper_status.get("recent_outcomes", []),
        }
        if self._last_run is not None:
            status["last_run_ts"] = self._last_run
        return status

    @property
    def cadence(self) -> float:
        return self._cadence


__all__ = ["CuriosityLoopDaemon"]

