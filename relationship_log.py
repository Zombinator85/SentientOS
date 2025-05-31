import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

import doctrine
import presence_ledger as pl

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
    # mirror to presence ledger and public feed
    pl.log(user, event, note)
    doctrine.log_json(
        doctrine.PUBLIC_LOG,
        {"time": time.time(), "event": event, "user": user},
    )


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

def _parse_ts(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.utcnow()


def last_recap_time(user: str) -> datetime:
    for entry in reversed(history(user, limit=1000)):
        if entry.get("event") == "recap":
            return _parse_ts(entry.get("time", ""))
    return datetime.min


def generate_recap(user: str) -> str:
    last_recap = last_recap_time(user)
    mem_count = 0
    from memory_manager import RAW_PATH

    for fp in RAW_PATH.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        ts = data.get("timestamp")
        if ts and _parse_ts(ts) > last_recap:
            mem_count += 1

    affirmations = [
        e
        for e in doctrine.consent_history(user)
        if _parse_ts(str(e.get("time", 0))) > last_recap
    ]
    amendments = [
        e
        for e in doctrine.history(50)
        if _parse_ts(str(e.get("time", 0))) > last_recap
    ]

    msg = (
        f"Since {last_recap.isoformat() if last_recap != datetime.min else 'the beginning'}, "
        f"{mem_count} memories, {len(affirmations)} affirmations and {len(amendments)} amendments were recorded."
    )
    log_event("recap", user, msg)
    doctrine.log_json(doctrine.PUBLIC_LOG, {"time": time.time(), "event": "recap", "user": user, "summary": msg})
    return msg


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
