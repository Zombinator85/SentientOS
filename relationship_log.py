import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

LOG_PATH = Path(os.getenv("RELATIONSHIP_LOG", "logs/relationship_log.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_event(event: str, user: str, note: str = "") -> None:
    entry = {
        "time": datetime.utcnow().isoformat(),
        "event": event,
        "user": user,
        "note": note,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def history(user: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    if user:
        lines = [ln for ln in lines if f'"user": "{user}"' in ln]
    lines = lines[-limit:]
    out: List[Dict[str, Any]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def recap(user: str) -> str:
    entries = history(user, limit=1000)
    if not entries:
        return "No shared history recorded."
    first = entries[0]
    last = entries[-1]
    msg = (
        f"You first affirmed the liturgy on {first['time']}. "
        f"Your last recorded event was '{last['event']}' on {last['time']}."
    )
    return msg
