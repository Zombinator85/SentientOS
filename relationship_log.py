"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from cathedral_const import PUBLIC_LOG, log_json
from logging_config import get_log_path
import json
import os
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

import doctrine
import presence_ledger as pl

LOG_PATH = get_log_path("relationship_log.jsonl", "RELATIONSHIP_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_event(
    event: str,
    user: str,
    note: str = "",
    *,
    present: Optional[List[str]] = None,
    witnesses: Optional[List[str]] = None,
    cosign: Optional[List[str]] = None,
) -> str:
    """Record a ritual event and mirror it to the presence ledger."""
    entry_id = uuid.uuid4().hex[:8]
    entry = {
        "id": entry_id,
        "time": datetime.utcnow().isoformat(),
        "event": event,
        "user": user,
        "note": note,
        "present": present or [],
        "witnesses": witnesses or [],
        "cosign": cosign or [],
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    # mirror to presence ledger and public feed
    pl.log(user, event, note)
    log_json(
        PUBLIC_LOG,
        {"time": time.time(), "event": event, "user": user},
    )
    return entry_id


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


def get_event(event_id: str) -> Optional[Dict[str, Any]]:
    """Return a single event by id."""
    if not LOG_PATH.exists():
        return None
    with LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if entry.get("id") == event_id:
                return entry
    return None

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
    log_json(PUBLIC_LOG, {"time": time.time(), "event": "recap", "user": user, "summary": msg})
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
