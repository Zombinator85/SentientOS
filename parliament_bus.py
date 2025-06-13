"""Async event bus for reasoning turns."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncGenerator
import uuid


class ParliamentBus:
    """In-memory async bus storing reasoning turns."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._log: list[dict[str, Any]] = []
        self.cycle_id: str = uuid.uuid4().hex

    async def publish(self, turn: dict[str, Any]) -> None:
        """Publish ``turn`` to all subscribers."""
        self._log.append(turn)
        for q in list(self._subscribers):
            await q.put(turn)

    async def subscribe(self) -> AsyncGenerator[dict[str, Any], None]:
        """Yield turns as they arrive."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.append(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subscribers.remove(q)

    def export(self, path: Path | None = None) -> Path:
        """Export stored turns to ``path`` and return it."""
        if path is None:
            path = Path("logs/reasoning") / f"{self.cycle_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for item in self._log:
                f.write(json.dumps(item) + "\n")
        return path


bus = ParliamentBus()
