"""Minimal safety shadow log used for privacy sensitive workflows."""

from __future__ import annotations

import os
import time
from collections import deque
from pathlib import Path
from typing import Iterable


LOG_PATH = Path(os.getenv("SAFETY_LOG_PATH", "logs/safety.log"))


def _ensure_parent() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_event(code: str) -> None:
    if os.getenv("SAFETY_LOG_ENABLED", "0") != "1":
        return
    _ensure_parent()
    line = f"{int(time.time())} {code}\n"
    with open(LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(line)
    _truncate_if_needed()


def _truncate_if_needed() -> None:
    limit_kb = int(os.getenv("SAFETY_LOG_MAX_KB", "128"))
    limit_bytes = max(1024, limit_kb * 1024)
    if not LOG_PATH.exists() or LOG_PATH.stat().st_size <= limit_bytes:
        return
    lines = deque(LOG_PATH.read_text(encoding="utf-8").splitlines(), maxlen=5000)
    # keep newest entries until size drops below limit
    pruned: list[str] = []
    size = 0
    for entry in reversed(lines):
        encoded = (entry + "\n").encode("utf-8")
        size += len(encoded)
        pruned.append(entry)
        if size >= limit_bytes:
            break
    pruned.reverse()
    LOG_PATH.write_text("\n".join(pruned) + ("\n" if pruned else ""), encoding="utf-8")


def count_recent_events(hours: int = 1) -> int:
    if not LOG_PATH.exists():
        return 0
    now = time.time()
    window = hours * 3600
    count = 0
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            ts_str, _code = line.split(" ", 1)
            ts = int(ts_str)
        except ValueError:
            continue
        if now - ts <= window:
            count += 1
    return count


def last_event_code(code: str) -> int | None:
    if not LOG_PATH.exists():
        return None
    for line in reversed(LOG_PATH.read_text(encoding="utf-8").splitlines()):
        if line.endswith(f" {code}"):
            try:
                return int(line.split(" ", 1)[0])
            except ValueError:
                return None
    return None


__all__ = ["log_event", "count_recent_events", "last_event_code", "LOG_PATH"]
