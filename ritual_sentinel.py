from logging_config import get_log_path
import time
from pathlib import Path

CONFESSION_FILE = get_log_path("confessional_log.jsonl")
HERESY_FILE = get_log_path("heresy_log.jsonl")
PAUSE_LOG = get_log_path("moment_of_pause.log")


def _trigger(event: str, line: str) -> None:
    entry = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} | {event} | {line.strip()}"
    with PAUSE_LOG.open("a", encoding="utf-8") as f:
        f.write(entry + "\n")
    print(entry)


def watch(interval: float = 2.0) -> None:  # pragma: no cover - runtime loop
    files = {
        "confession": CONFESSION_FILE,
        "heresy": HERESY_FILE,
    }
    pos = {k: (p.stat().st_size if p.exists() else 0) for k, p in files.items()}
    print("[SENTINEL] watching logs...")
    while True:
        for name, path in files.items():
            if not path.exists():
                continue
            size = path.stat().st_size
            if size > pos[name]:
                with path.open("r", encoding="utf-8") as f:
                    f.seek(pos[name])
                    for line in f:
                        _trigger(name, line)
                pos[name] = size
        time.sleep(interval)


if __name__ == "__main__":  # pragma: no cover - manual
    watch()
