"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import os
import json
from pathlib import Path
from typing import Any, Dict, List
import datetime
from api import actuator

MEMORY_DIR = get_log_path("memory", "MEMORY_DIR")
SUB_PATH = MEMORY_DIR / "subscriptions.json"
EVENT_PATH = MEMORY_DIR / "events.jsonl"
SUB_PATH.parent.mkdir(parents=True, exist_ok=True)
EVENT_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load() -> Dict[str, List[Dict[str, Any]]]:
    if SUB_PATH.exists():
        try:
            return json.loads(SUB_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(data: Dict[str, List[Dict[str, Any]]]) -> None:
    SUB_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_subscription(event: str, method: str, target: str | None = None) -> None:
    data = _load()
    data.setdefault(event, []).append({"method": method, "target": target})
    _save(data)


def remove_subscription(event: str, method: str, target: str | None = None) -> None:
    data = _load()
    entries = data.get(event, [])
    data[event] = [e for e in entries if not (e.get("method") == method and e.get("target") == target)]
    _save(data)


def list_subscriptions() -> Dict[str, List[Dict[str, Any]]]:
    return _load()


def _log_event(event: str, payload: Dict[str, Any]) -> None:
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "event": event,
        "payload": payload,
    }
    with open(EVENT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def list_events(limit: int = 10) -> List[Dict[str, Any]]:
    if not EVENT_PATH.exists():
        return []
    lines = EVENT_PATH.read_text(encoding="utf-8").splitlines()
    out: List[Dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def send(event: str, payload: Dict[str, Any]) -> None:
    _log_event(event, payload)
    subs = _load().get(event, [])
    for s in subs:
        method = s.get("method")
        tgt = s.get("target", "")
        try:
            if method == "email":
                actuator.send_email(tgt, f"Event: {event}", json.dumps(payload))
            elif method == "webhook":
                actuator.trigger_webhook(tgt, payload)
            else:
                print(f"[NOTIFY] {event}: {payload}")
        except Exception as e:  # pragma: no cover - defensive
            print(f"[NOTIFY ERROR] {e}")
