"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Self-reflection and self-healing manager."""
import json
import datetime
from pathlib import Path
from typing import Any, Dict, Optional, cast

try:
    import yaml  # type: ignore[import-untyped]  # optional YAML support
except Exception:  # pragma: no cover - optional
    yaml = None

import memory_manager as mm
import notification
import self_patcher
from api import actuator
import workflow_controller

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
        self.last_event_ts: Optional[str] = cast(Optional[str], self.state.get("last_event_ts"))
        self.last_log_id: Optional[str] = cast(Optional[str], self.state.get("last_log_id"))
        self.failure_counts: Dict[str, int] = cast(Dict[str, int], self.state.get("wf_failures", {}))

    def _record(self, parent: str, reason: str, next_step: str | None = None) -> None:
        mm.save_reflection(parent=parent, intent={}, result=None, reason=reason, next_step=next_step, plugin="self_heal")

    def _handle_log(self, log: Dict[str, Any]) -> None:
        if log.get("status") == "failed":
            reason = f"Failure: {log.get('error')}"
            self._record(log.get("id", ""), reason, next_step="auto_patch")
            self_patcher.propose_patch(reason)
        else:
            reason = f"Success: {log.get('intent', {}).get('type')}"
            self._record(log.get("id", ""), reason)

    def process_logs(self) -> None:
        logs = actuator.recent_logs(last=20)
        for log in logs:
            log_id = cast(Optional[str], log.get("id"))
            ts = cast(Optional[str], log.get("timestamp"))
            if self.last_log_id and log_id and log_id <= self.last_log_id:
                continue
            self.last_log_id = log_id
            self._handle_log(log)

    def _handle_event(self, event: Dict[str, Any]) -> None:
        name = str(event.get("event", ""))
        payload = cast(Dict[str, Any], event.get("payload", {}))
        parent = str(payload.get("id") or event.get("id") or name)
        if name.startswith("patch_") or name == "self_patch":
            reason = f"Patch event {name}"
            self._record(parent, reason)
        elif name.endswith("_error"):
            reason = f"Event error: {name}"
            self._record(parent, reason, next_step="investigate")
        elif name.startswith("input.") or name.startswith("ui."):
            if event.get("status") != "ok":
                reason = f"System control failure: {event.get('error', '')}"
                self._record(parent, reason, next_step="undo")
        elif name == "workflow.step" and payload.get("status") == "failed":
            wf = str(payload.get("workflow", ""))
            step = str(payload.get("step", ""))
            key = f"{wf}:{step}"
            count = self.failure_counts.get(key, 0) + 1
            self.failure_counts[key] = count
            if count >= 3:
                self._record(parent, f"Auto-heal {key}", next_step="auto_heal")
                self._auto_heal_workflow(wf, step)
                self.failure_counts[key] = 0

    def process_events(self) -> None:
        events = notification.list_events(20)
        for ev in events:
            ts = cast(Optional[str], ev.get("timestamp"))
            if self.last_event_ts and ts and ts <= self.last_event_ts:
                continue
            self.last_event_ts = ts
            self._handle_event(ev)

    def _auto_heal_workflow(self, wf: str, step: str) -> None:
        path = workflow_controller.WORKFLOW_FILES.get(wf)
        if not path:
            return
        try:
            text = path.read_text(encoding="utf-8")
            if path.suffix in {".yml", ".yaml"}:
                data = yaml.safe_load(text) if yaml else workflow_controller._load_yaml(text)
            else:
                data = json.loads(text)
            for st in data.get("steps", []):
                if st.get("name") == step:
                    st["skip"] = True
            if path.suffix in {".yml", ".yaml"} and yaml:
                new_text = yaml.safe_dump(data)
            else:
                new_text = json.dumps(data, indent=2)
            path.write_text(new_text, encoding="utf-8")
            try:
                import workflow_review as wr
                wr.flag_for_review(wf, text, new_text)
            except Exception:
                pass
        except Exception:
            pass

    def run_cycle(self) -> None:
        # Process events first so log-based reflections remain the most recent
        self.process_events()
        self.process_logs()
        self.state["last_event_ts"] = self.last_event_ts
        self.state["last_log_id"] = self.last_log_id
        self.state["wf_failures"] = self.failure_counts
        _save_state(self.state)
