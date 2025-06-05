from logging_config import get_log_path
import time
from pathlib import Path
from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
LOG_PATH = get_log_path("user_presence.jsonl")


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


def main() -> None:
    require_admin_banner()
    monitor()


if __name__ == "__main__":
    main()
