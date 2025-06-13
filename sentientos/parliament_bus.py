# Sanctuary privilege ritual must appear before any code or imports
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""Simple in-memory event bus for conversation turns."""

from queue import SimpleQueue
from typing import Callable, Dict, Any, Iterable

_TURN_QUEUE: SimpleQueue[dict[str, Any]] = SimpleQueue()
_LISTENERS: list[Callable[[dict[str, Any]], None]] = []


def publish(turn: dict[str, Any]) -> None:
    """Publish a turn to the bus."""
    _TURN_QUEUE.put(turn)
    for cb in list(_LISTENERS):
        try:
            cb(turn)
        except Exception:
            pass


def stream() -> Iterable[dict[str, Any]]:
    """Yield turns as they arrive."""
    while True:
        yield _TURN_QUEUE.get()


def subscribe(callback: Callable[[dict[str, Any]], None]) -> None:
    """Register a listener for new turns."""
    _LISTENERS.append(callback)
