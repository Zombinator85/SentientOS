import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

LEDGER_PATH = Path(os.getenv("FORGIVENESS_LEDGER", "logs/forgiveness_ledger.jsonl"))
LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_forgiveness(event_ts: str, user: str, penance: str, officiant: str) -> Dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_ts": event_ts,
        "user": user,
        "penance": penance,
        "officiant": officiant,
    }
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, Any]]:
    if not LEDGER_PATH.exists():
        return []
    lines = LEDGER_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    out: List[Dict[str, Any]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out
