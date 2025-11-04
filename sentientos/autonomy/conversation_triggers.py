"""Proactive conversation orchestrator."""

from __future__ import annotations

import datetime as _dt
import time
from dataclasses import dataclass
from typing import Mapping, Optional

from sentientos.metrics import MetricsRegistry


@dataclass
class ConversationConfig:
    enable: bool = False
    quiet_hours: str = "22:00-07:00"
    trigger_on_user_presence: bool = True
    trigger_on_novelty: bool = True
    trigger_on_name: bool = True
    max_prompts_per_hour: int = 6


class ConversationTriggers:
    def __init__(
        self,
        config: ConversationConfig,
        *,
        metrics: MetricsRegistry | None = None,
        clock: callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._metrics = metrics or MetricsRegistry()
        self._clock = clock or time.time
        self._window: list[float] = []
        self._quiet_start, self._quiet_end = self._parse_quiet_hours(config.quiet_hours)

    def should_trigger(self, trigger_type: str, *, payload: Mapping[str, object] | None = None) -> bool:
        if not self._config.enable:
            return False
        if trigger_type == "presence" and not self._config.trigger_on_user_presence:
            return False
        if trigger_type == "novelty" and not self._config.trigger_on_novelty:
            return False
        if trigger_type == "name" and not self._config.trigger_on_name:
            return False
        now = self._clock()
        if self._within_quiet_hours(now):
            return False
        self._window = [ts for ts in self._window if ts >= now - 3600.0]
        if len(self._window) >= max(int(self._config.max_prompts_per_hour), 0):
            return False
        self._window.append(now)
        self._metrics.increment("sos_conversation_triggers_total", labels={"type": trigger_type})
        return True

    def _within_quiet_hours(self, now: float) -> bool:
        if self._quiet_start is None or self._quiet_end is None:
            return False
        current = _dt.datetime.fromtimestamp(now)
        start = current.replace(hour=self._quiet_start[0], minute=self._quiet_start[1], second=0, microsecond=0)
        end = current.replace(hour=self._quiet_end[0], minute=self._quiet_end[1], second=0, microsecond=0)
        if self._quiet_start == self._quiet_end:
            return False
        if self._quiet_start < self._quiet_end:
            return start <= current < end
        return current >= start or current < end

    def _parse_quiet_hours(self, value: str) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
        if not value:
            return (None, None)
        parts = value.split("-")
        if len(parts) != 2:
            return (None, None)
        return self._parse_time(parts[0]), self._parse_time(parts[1])

    def _parse_time(self, value: str) -> tuple[int, int] | None:
        try:
            hour, minute = value.split(":")
            return int(hour), int(minute)
        except Exception:
            return None

    def status(self) -> Mapping[str, object]:
        return {
            "status": "healthy" if self._config.enable else "disabled",
            "quiet_hours": self._config.quiet_hours,
            "max_prompts_per_hour": self._config.max_prompts_per_hour,
            "recent_triggers": len(self._window),
        }


__all__ = ["ConversationConfig", "ConversationTriggers"]

