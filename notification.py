import os
import json
from pathlib import Path
from typing import Any, Dict, List
from api import actuator

MEMORY_DIR = Path(os.getenv("MEMORY_DIR", "logs/memory"))
SUB_PATH = MEMORY_DIR / "subscriptions.json"
SUB_PATH.parent.mkdir(parents=True, exist_ok=True)


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


def send(event: str, payload: Dict[str, Any]) -> None:
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
