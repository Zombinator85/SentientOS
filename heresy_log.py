import json
import os
from datetime import datetime
from pathlib import Path

LOG_PATH = Path(os.getenv("HERESY_LOG", "logs/heresy_log.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log(action: str, requestor: str, detail: str) -> None:
    """Append a heresy event to the immutable log."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "requestor": requestor,
        "detail": detail,
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def tail(limit: int = 10) -> list[dict]:
    """Return the most recent log entries."""
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    out: list[dict] = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def search(term: str) -> list[dict]:
    """Search log lines containing a term."""
    if not LOG_PATH.exists():
        return []
    results = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if term in line:
            try:
                results.append(json.loads(line))
            except Exception:
                continue
    return results
