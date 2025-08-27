#!/usr/bin/env python3
"""Minimal SentientOS boot init script (boot seal v0.1)."""

import os
import threading
import time
from pathlib import Path

MOUNT_POINTS = [Path("/vow"), Path("/glow"), Path("/daemon"), Path("/pulse")]
HEARTBEAT_LOG = Path("/daemon/logs/heartbeat.log")


def ensure_mounts() -> None:
    for path in MOUNT_POINTS:
        path.mkdir(parents=True, exist_ok=True)


def load_model():
    print("Loading GPT-OSS model (placeholder)")
    return object()


def boot_message() -> None:
    try:
        with open("NEWLEGACY.txt", "r", encoding="utf-8") as f:
            lines = [next(f).rstrip("\n") for _ in range(3)]
    except (FileNotFoundError, StopIteration):
        lines = ["NEWLEGACY.txt missing or incomplete."]
    for line in lines:
        print(line)


def heartbeat(stop: threading.Event) -> None:
    HEARTBEAT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(HEARTBEAT_LOG, "a", encoding="utf-8") as log:
        while not stop.is_set():
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} heartbeat\n")
            log.flush()
            if stop.wait(30):
                break


def main() -> None:
    ensure_mounts()
    load_model()
    boot_message()

    stop = threading.Event()
    thread = threading.Thread(target=heartbeat, args=(stop,), daemon=True)
    thread.start()

    try:
        while True:
            try:
                user_input = input("\U0001F56F\uFE0F ")
            except EOFError:
                break
            if user_input.strip().lower() == "shutdown":
                break
            print(user_input)
    finally:
        stop.set()
        thread.join()
        print("Shutting down...")


if __name__ == "__main__":
    main()
