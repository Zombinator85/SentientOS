import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import json
import os

LEDGER_PATH = Path(os.getenv("USER_PRESENCE_LOG", "logs/user_presence.jsonl"))
LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)


def log(user: str, event: str, note: str = "") -> None:
    """Record a general presence event."""
    entry = {
        "time": datetime.utcnow().isoformat(),
        "user": user,
        "event": event,
        "note": note,
    }
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def log_privilege(
    user: str, platform: str, tool: str, status: str
) -> None:
    """Record a privilege check attempt."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": "admin_privilege_check",
        "status": status,
        "user": user,
        "platform": platform,
        "tool": tool,
    }
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def history(user: str, limit: int = 20) -> List[Dict[str, str]]:
    if not LEDGER_PATH.exists():
        return []
    lines = [
        ln for ln in LEDGER_PATH.read_text(encoding="utf-8").splitlines()
        if f'"user": "{user}"' in ln
    ][-limit:]
    out: List[Dict[str, str]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def recent_privilege_attempts(limit: int = 5) -> List[Dict[str, str]]:
    """Return the most recent privilege check entries."""
    if not LEDGER_PATH.exists():
        return []
    lines = reversed(LEDGER_PATH.read_text(encoding="utf-8").splitlines())
    out: List[Dict[str, str]] = []
    for ln in lines:
        try:
            entry = json.loads(ln)
        except Exception:
            continue
        if entry.get("event") == "admin_privilege_check":
            out.append(entry)
            if len(out) == limit:
                break
    return list(reversed(out))
