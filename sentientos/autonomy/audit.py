"""Audit helpers for autonomy action tracing.

This module centralises how GUI, browser and other embodied subsystems
record their activity.  Log entries are persisted to
``logs/autonomy_actions.jsonl`` so that operators can inspect recent
actions via the admin dashboard or command line helpers.  The helper is
intentionally lightweight so it can be imported without pulling in FastAPI
or other optional dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Lock
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_log_path() -> Path:
    root = Path(os.getenv("SENTIENTOS_ACTION_LOG", "logs/autonomy_actions.jsonl"))
    root.parent.mkdir(parents=True, exist_ok=True)
    return root


@dataclass
class AutonomyAction:
    """Structured representation of an autonomy action."""

    module: str
    action: str
    status: str
    timestamp: str = field(default_factory=_utcnow)
    details: MutableMapping[str, object] = field(default_factory=dict)

    def to_json(self) -> str:
        payload = {
            "timestamp": self.timestamp,
            "module": self.module,
            "action": self.action,
            "status": self.status,
        }
        if self.details:
            payload.update(self.details)
        return json.dumps(payload, ensure_ascii=False)


class AutonomyActionLogger:
    """Persist and retrieve audit entries for embodied actions."""

    def __init__(self, *, path: Optional[Path] = None, history_size: int = 200) -> None:
        self._path = path or _default_log_path()
        self._history_size = max(int(history_size), 1)
        self._lock = Lock()

    @property
    def path(self) -> Path:
        return self._path

    def log(self, module: str, action: str, status: str, **details: object) -> None:
        entry = AutonomyAction(module=module, action=action, status=status, details=dict(details))
        record = entry.to_json()
        with self._lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(record + "\n")
            self._trim_locked()

    def _trim_locked(self) -> None:
        if self._history_size <= 0 or not self._path.exists():
            return
        lines = self._path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= self._history_size:
            return
        keep = lines[-self._history_size :]
        self._path.write_text("\n".join(keep) + "\n", encoding="utf-8")

    def recent(self, limit: int = 50, *, modules: Iterable[str] | None = None) -> List[Mapping[str, object]]:
        limit = max(int(limit), 1)
        module_filter = {m for m in modules} if modules else None
        if not self._path.exists():
            return []
        with self._lock:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        items: List[Mapping[str, object]] = []
        for raw in reversed(lines):
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if module_filter and parsed.get("module") not in module_filter:
                continue
            items.append(parsed)
            if len(items) >= limit:
                break
        items.reverse()
        return items

    def summary(self) -> Mapping[str, object]:
        """Return a compact summary for dashboard consumption."""

        recent = self.recent(20)
        totals: Dict[str, int] = {}
        blocked = 0
        for entry in recent:
            module = str(entry.get("module", "unknown"))
            totals[module] = totals.get(module, 0) + 1
            if entry.get("status") == "blocked":
                blocked += 1
        return {
            "recent": recent,
            "totals": totals,
            "blocked_recent": blocked,
        }


__all__ = ["AutonomyAction", "AutonomyActionLogger"]

