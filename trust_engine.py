import os
import json
import uuid
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import difflib

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None

TRUST_DIR = Path(os.getenv("TRUST_DIR", "logs/trust"))
EVENTS_PATH = TRUST_DIR / "events.jsonl"
POLICIES_DIR = TRUST_DIR / "policies"
FEEDBACK_PATH = TRUST_DIR / "feedback.jsonl"
LOCKS_FILE = POLICIES_DIR / "locks.json"

TRUST_DIR.mkdir(parents=True, exist_ok=True)
POLICIES_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def log_event(event_type: str, cause: str, explanation: str, source: str,
              data: Optional[Dict[str, Any]] = None) -> str:
    """Append an event entry and return its ID."""
    event_id = uuid.uuid4().hex[:8]
    entry = {
        "id": event_id,
        "timestamp": _now(),
        "type": event_type,
        "cause": cause,
        "explanation": explanation,
        "source": source,
        "data": data or {},
    }
    with EVENTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return event_id


def list_events(limit: int = 20) -> List[Dict[str, Any]]:
    """Return the most recent events."""
    if not EVENTS_PATH.exists():
        return []
    lines = EVENTS_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(l) for l in lines[-limit:]]


def get_event(event_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single event by ID."""
    if not EVENTS_PATH.exists():
        return None
    with EVENTS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("id") == event_id:
                return entry
    return None


def add_feedback(event_id: str, feedback: str, user: str = "user") -> str:
    """Record feedback related to an event."""
    fb_id = uuid.uuid4().hex[:8]
    entry = {
        "id": fb_id,
        "event_id": event_id,
        "timestamp": _now(),
        "user": user,
        "feedback": feedback,
    }
    with FEEDBACK_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return fb_id


def _policy_versions(name: str) -> List[Path]:
    return sorted(POLICIES_DIR.glob(f"{name}_*.json"))


def load_policy(name: str) -> Dict[str, Any]:
    vers = _policy_versions(name)
    if not vers:
        return {}
    return json.loads(vers[-1].read_text(encoding="utf-8"))


def update_policy(name: str, data: Dict[str, Any], source: str, explanation: str) -> str:
    """Update policy and log diff."""
    old = load_policy(name)
    new_text = json.dumps(data, indent=2)
    old_text = json.dumps(old, indent=2)
    diff = list(difflib.unified_diff(old_text.splitlines(), new_text.splitlines(), lineterm=""))
    ts = _now().replace(":", "-")
    dest = POLICIES_DIR / f"{name}_{ts}.json"
    dest.write_text(new_text, encoding="utf-8")
    return log_event("policy_change", f"policy:{name}", explanation, source, {"diff": diff})


def diff_policy(name: str) -> List[str]:
    vers = _policy_versions(name)
    if len(vers) < 2:
        return []
    old = vers[-2].read_text(encoding="utf-8")
    new = vers[-1].read_text(encoding="utf-8")
    return list(difflib.unified_diff(old.splitlines(), new.splitlines(), fromfile=vers[-2].name, tofile=vers[-1].name, lineterm=""))


def rollback_policy(name: str, version_index: int = -2) -> Optional[str]:
    vers = _policy_versions(name)
    if len(vers) < abs(version_index):
        return None
    target = vers[version_index]
    data = json.loads(target.read_text(encoding="utf-8"))
    update_policy(name, data, "rollback", f"Rollback to {target.name}")
    return target.name


def _load_locks() -> Dict[str, Any]:
    if LOCKS_FILE.exists():
        return json.loads(LOCKS_FILE.read_text(encoding="utf-8"))
    return {}


def _save_locks(data: Dict[str, Any]) -> None:
    LOCKS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def lock_policy(name: str, user: str, reason: str) -> str:
    locks = _load_locks()
    locks[name] = {"locked": True, "user": user, "reason": reason, "timestamp": _now()}
    _save_locks(locks)
    return log_event("lock", f"policy:{name}", reason, user)


def unlock_policy(name: str, user: str, reason: str) -> str:
    locks = _load_locks()
    locks[name] = {"locked": False, "user": user, "reason": reason, "timestamp": _now()}
    _save_locks(locks)
    return log_event("unlock", f"policy:{name}", reason, user)

