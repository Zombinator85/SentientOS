from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, Optional


@dataclass
class TemporalState:
    date: str
    last_seen: str
    session_id: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, object], *, fallback: "TemporalState") -> "TemporalState":
        try:
            return cls(
                date=str(payload.get("date") or fallback.date),
                last_seen=str(payload.get("last_seen") or fallback.last_seen),
                session_id=str(payload.get("session_id") or fallback.session_id),
            )
        except Exception:
            return fallback


class ChronosDaemon:
    """Track wall-clock boundaries and surface day/session transitions."""

    def __init__(
        self, state_path: Path | str = "temporal_state.json", *, now_fn: Optional[Callable[[], datetime]] = None
    ) -> None:
        self.state_path = Path(state_path)
        self._now = now_fn or (lambda: datetime.now().astimezone())
        bootstrap = self._now()
        self._startup = bootstrap
        self._state = self._load_state(default_date=bootstrap)

    def _load_state(self, *, default_date: datetime) -> TemporalState:
        fallback = TemporalState(
            date=default_date.date().isoformat(),
            last_seen=default_date.isoformat(),
            session_id=hashlib.sha256(default_date.isoformat().encode("utf-8")).hexdigest()[:12],
        )
        if not self.state_path.exists():
            return fallback
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return fallback
        return TemporalState.from_payload(payload, fallback=fallback)

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with self.state_path.open("w", encoding="utf-8") as f:
            json.dump(asdict(self._state), f, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def tick(self, *, summary_pointer: str | None = None) -> Mapping[str, object]:
        now = self._now()
        now_local = now.astimezone()
        current_date = now_local.date().isoformat()
        new_day = current_date != self._state.date
        event: Mapping[str, object] | None = None
        if new_day:
            day_hash = hashlib.sha256(f"{current_date}-{self._state.session_id}".encode("utf-8")).hexdigest()[:16]
            event = {
                "type": "new_day",
                "date": current_date,
                "day_hash": day_hash,
                "summary_pointer": summary_pointer,
            }
            self._state.date = current_date
        self._state.last_seen = now_local.isoformat()
        self._persist()
        snapshot = {
            "timestamp": now_local.isoformat(),
            "timezone": str(now_local.tzinfo),
            "uptime_seconds": (now_local - self._startup).total_seconds(),
            "new_day": new_day,
            "state_path": str(self.state_path),
        }
        if event:
            snapshot["event"] = event
        return snapshot

    def is_new_day(self) -> bool:
        current_date = self._now().astimezone().date().isoformat()
        return current_date != self._state.date

    def state(self) -> TemporalState:
        return self._state


__all__ = ["ChronosDaemon", "TemporalState"]
