from logging_config import get_log_path
import json
import os
import sys
import time
from pathlib import Path

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
LOG_PATH = get_log_path("user_presence.jsonl", "USER_PRESENCE_LOG")


def pulse_loop(period: float = 1.0) -> None:
    last_size = 0
    while True:
        try:
            size = LOG_PATH.stat().st_size
        except FileNotFoundError:
            size = 0
        if size != last_size:
            sys.stdout.write("\u2665\n")
            sys.stdout.flush()
            last_size = size
        time.sleep(period)


if __name__ == "__main__":
    pulse_loop()
