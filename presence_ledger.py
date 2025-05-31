import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LEDGER_PATH = Path(os.getenv("USER_PRESENCE_LOG", "logs/user_presence.jsonl"))
LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)


def log(user: str, event: str, note: str = "") -> None:
    entry = {
        "time": datetime.utcnow().isoformat(),
        "user": user,
        "event": event,
        "note": note,
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
