import json
import os
import sys
import time
from pathlib import Path

LOG_PATH = Path(os.getenv("USER_PRESENCE_LOG", "logs/user_presence.jsonl"))


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
