import os
import json
import datetime
from pathlib import Path

ANNIVERSARY = os.getenv("CATHEDRAL_BIRTH", "2023-01-01")
LOG_FILE = Path("logs/anniversary_log.jsonl")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def check_and_log() -> None:
    today = datetime.date.today().isoformat()[5:]
    ann = ANNIVERSARY[5:]
    if today == ann:
        entry = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "event": "anniversary",
            "message": "Presence recap",
        }
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        print("Anniversary blessing recorded")


if __name__ == "__main__":  # pragma: no cover - manual
    check_and_log()
