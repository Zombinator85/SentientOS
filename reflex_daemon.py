from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Iterable, Optional, Protocol


class ReflexContext(Protocol):
    epoch: str | None

    def allow_reflex(self) -> bool:
        ...


class BaseTrigger:
    def pop_event(self, now: float, event: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        return None

    def reset(self) -> None:
        pass


class IntervalTrigger(BaseTrigger):
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self._next_fire: float | None = None

    def pop_event(self, now: float, event: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if self._next_fire is None:
            self._next_fire = now + self.seconds
            return None
        if now >= self._next_fire:
            self._next_fire = now + self.seconds
            return {"reason": "interval", "interval": self.seconds}
        return None

    def reset(self) -> None:
        self._next_fire = None


class OnDemandTrigger(BaseTrigger):
    def __init__(self) -> None:
        self._pending: Deque[Dict[str, Any]] = deque()

    def fire(self, agent: str | None = None, persona: str | None = None, payload: Optional[Dict[str, Any]] = None) -> None:
        self._pending.append({"agent": agent, "persona": persona, "payload": payload or {}})

    def pop_event(self, now: float, event: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if self._pending:
            fired = self._pending.popleft()
            fired["reason"] = "on_demand"
            return fired
        return None


class ConditionalTrigger(BaseTrigger):
    def __init__(self, check: Callable[[], bool], interval: float = 1.0) -> None:
        self.check = check
        self.interval = interval
        self._next_check: float | None = None

    def pop_event(self, now: float, event: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if self._next_check is None or now >= self._next_check:
            self._next_check = now + self.interval
            if self.check():
                return {"reason": "conditional"}
        return None

    def reset(self) -> None:
        self._next_check = None


class FileChangeTrigger(BaseTrigger):
    def __init__(self, path: str, interval: float = 1.0) -> None:
        self.path = Path(path)
        self.interval = interval
        self._next_check: float | None = None
        self._last_mtime = self._scan_latest_mtime()

    def _scan_latest_mtime(self) -> float:
        latest = 0.0
        if not self.path.exists():
            return latest
        if self.path.is_file():
            try:
                return self.path.stat().st_mtime
            except OSError:
                return latest
        for entry in self.path.rglob("*"):
            if not entry.is_file():
                continue
            try:
                latest = max(latest, entry.stat().st_mtime)
            except OSError:
                continue
        return latest

    def pop_event(self, now: float, event: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if self._next_check is None or now >= self._next_check:
            self._next_check = now + self.interval
            latest = self._scan_latest_mtime()
            if latest > self._last_mtime:
                self._last_mtime = latest
                return {"reason": "file_change", "path": str(self.path)}
        return None

    def reset(self) -> None:
        self._next_check = None
        self._last_mtime = self._scan_latest_mtime()


@dataclass
class ReflexQueueItem:
    rule: Any
    agent: str | None
    persona: str | None
    event: Dict[str, Any]
    queued_at: float


@dataclass
class ReflexDaemon:
    rules: list[Any] = field(default_factory=list)
    queue: Deque[ReflexQueueItem] = field(default_factory=deque)

    def add_rule(self, rule: Any) -> None:
        self.rules.append(rule)

    def maybe_trigger_reflexes(
        self,
        context: ReflexContext,
        *,
        event: Optional[Dict[str, Any]] = None,
        now: Optional[float] = None,
    ) -> int:
        if context is None or not context.allow_reflex() or not context.epoch:
            return 0
        current = time.time() if now is None else now
        queued = 0
        for rule in self.rules:
            trigger = getattr(rule, "trigger", None)
            if trigger is None or getattr(rule, "frozen", False):
                continue
            fired = trigger.pop_event(current, event)
            if fired is None:
                continue
            agent = fired.get("agent") if isinstance(fired, dict) else None
            persona = fired.get("persona") if isinstance(fired, dict) else None
            payload = fired if isinstance(fired, dict) else {"reason": "trigger"}
            self.queue.append(
                ReflexQueueItem(
                    rule=rule,
                    agent=agent,
                    persona=persona,
                    event=payload,
                    queued_at=current,
                )
            )
            queued += 1
        return queued

    def drain_queue(self) -> Iterable[ReflexQueueItem]:
        while self.queue:
            yield self.queue.popleft()

    def reset(self) -> None:
        self.queue.clear()
        for rule in self.rules:
            trigger = getattr(rule, "trigger", None)
            if trigger is not None:
                trigger.reset()
