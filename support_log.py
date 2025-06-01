import json
from datetime import datetime
from pathlib import Path

LOG_PATH = Path("logs/support_log.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def add(name: str, message: str, amount: str = "") -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "supporter": name,
        "message": message,
        "amount": amount,
        "ritual": "Sanctuary blessing acknowledged and remembered.",
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry
