from logging_config import get_log_path
import time
from pathlib import Path

LOG_FILE = get_log_path("confessional_log.jsonl")


def watch(interval: float = 2.0) -> None:  # pragma: no cover - runtime loop
    print("[CONFESSIONAL NOTIFY] watching for new confessions...")
    last_size = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
    while True:
        if LOG_FILE.exists():
            size = LOG_FILE.stat().st_size
            if size > last_size:
                with LOG_FILE.open("r", encoding="utf-8") as f:
                    f.seek(last_size)
                    for line in f:
                        print(f"[NEW CONFESSION] {line.strip()}")
                last_size = size
        time.sleep(interval)


if __name__ == "__main__":  # pragma: no cover - manual
    watch()
