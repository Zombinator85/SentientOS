"""Self-reflection and self-healing manager."""
import json
import datetime
from pathlib import Path
from typing import Any, Dict

import memory_manager as mm
import notification
import self_patcher
from api import actuator

STATE_PATH = mm.MEMORY_DIR / "self_reflection_state.json"
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_state() -> Dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


class SelfHealingManager:
    """Monitor events and logs to generate critiques and healing actions."""

    def __init__(self) -> None:
        self.state = _load_state()
        self.last_event_ts = self.state.get("last_event_ts")
        self.last_log_id = self.state.get("last_log_id")

    def _record(self, parent: str, reason: str, next_step: str | None = None) -> None:
        mm.save_reflection(parent=parent, intent={}, result=None, reason=reason, next_step=next_step, plugin="self_heal")

    def _handle_log(self, log: Dict[str, Any]) -> None:
        if log.get("status") == "failed":
            reason = f"Failure: {log.get('error')}"
            self._record(log.get("id", ""), reason, next_step="auto_patch")
            self_patcher.apply_patch(reason, auto=True)
        else:
            reason = f"Success: {log.get('intent', {}).get('type')}"
            self._record(log.get("id", ""), reason)

    def process_logs(self) -> None:
        logs = actuator.recent_logs(last=20)
        for log in logs:
            log_id = log.get("id")
            ts = log.get("timestamp")
            if self.last_log_id and log_id <= self.last_log_id:
                continue
            self.last_log_id = log_id
            self._handle_log(log)

    def _handle_event(self, event: Dict[str, Any]) -> None:
        name = event.get("event")
        payload = event.get("payload", {})
        parent = payload.get("id", name)
        if name.startswith("patch_") or name == "self_patch":
            reason = f"Patch event {name}"
            self._record(parent, reason)
        elif name.endswith("_error"):
            reason = f"Event error: {name}"
            self._record(parent, reason, next_step="investigate")

    def process_events(self) -> None:
        events = notification.list_events(20)
        for ev in events:
            ts = ev.get("timestamp")
            if self.last_event_ts and ts <= self.last_event_ts:
                continue
            self.last_event_ts = ts
            self._handle_event(ev)

    def run_cycle(self) -> None:
        self.process_logs()
        self.process_events()
        self.state["last_event_ts"] = self.last_event_ts
        self.state["last_log_id"] = self.last_log_id
        _save_state(self.state)
