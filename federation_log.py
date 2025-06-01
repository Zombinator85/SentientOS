import os
import json
from datetime import datetime
from pathlib import Path

LOG_PATH = Path(os.getenv("FEDERATION_LOG", "logs/federation_log.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def add(peer: str, email: str = "", message: str = "Federation sync") -> dict:
    """Record a federation blessing entry."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "peer": peer,
        "email": email,
        "message": message,
        "ritual": "Federation blessing recorded."
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry
