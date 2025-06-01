import time
from pathlib import Path

LOG_PATH = Path("logs/user_presence.jsonl")


def monitor(period: float = 5.0, window: int = 60) -> None:
    last_count = 0
    while True:
        if LOG_PATH.exists():
            lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
            count = len(lines[-window:])
        else:
            count = 0
        print(f"Heartbeats last {window}s: {count}")
        if count > last_count:
            print("Spike detected")
        last_count = count
        time.sleep(period)


if __name__ == "__main__":
    monitor()
