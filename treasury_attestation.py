import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

LOG_PATH = Path("logs/treasury_attestations.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def add_attestation(log_id: str, user: str, origin: str, note: str = "") -> str:
    """Record a cross-site attestation or blessing for a log."""
    att_id = uuid.uuid4().hex[:8]
    entry = {
        "id": att_id,
        "time": datetime.utcnow().isoformat(),
        "log": log_id,
        "origin": origin,
        "user": user,
        "note": note,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return att_id


def history(log_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    if log_id:
        lines = [ln for ln in lines if f'"log": "{log_id}"' in ln]
    lines = lines[-limit:]
    out: List[Dict[str, Any]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out
