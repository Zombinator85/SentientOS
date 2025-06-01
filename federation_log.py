import json
from datetime import datetime
from pathlib import Path

LOG_PATH = Path("logs/federation_log.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def add(name: str, email: str = "", message: str = "") -> dict:
    """Record a federation blessing entry."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "peer": name,
        "email": email,
        "message": message,
        "ritual": "Federation blessing invoked and logged.",
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry
