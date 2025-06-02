from logging_config import get_log_path
import json
import os
import time
from pathlib import Path

HERESY_LOG = get_log_path("heresy_log.jsonl", "HERESY_LOG")


def monitor(period: float = 5.0) -> None:
    seen = 0
    while True:
        if not HERESY_LOG.exists():
            time.sleep(period)
            continue
        lines = HERESY_LOG.read_text(encoding="utf-8").splitlines()
        if len(lines) > seen:
            for ln in lines[seen:]:
                try:
                    data = json.loads(ln)
                except Exception:
                    continue
                print(f"Heresy alert: {data.get('action')} {data.get('detail')}")
            seen = len(lines)
        time.sleep(period)


if __name__ == "__main__":
    monitor()
