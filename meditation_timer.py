from logging_config import get_log_path
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
LOG_PATH = get_log_path("meditation_log.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def run_session(duration: int, note: str) -> dict:
    start = datetime.utcnow()
    print(f"Meditation started for {duration}s")
    time.sleep(duration)
    end = datetime.utcnow()
    entry = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "duration": duration,
        "note": note,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print("Session complete")
    return entry


def main() -> None:
    ap = argparse.ArgumentParser(description="Meditation timer")
    ap.add_argument("duration", type=int, help="Seconds")
    ap.add_argument("--note", default="")
    args = ap.parse_args()
    run_session(args.duration, args.note)


if __name__ == "__main__":
    main()
