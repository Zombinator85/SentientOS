"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import asyncio
from dataclasses import dataclass
from typing import AsyncGenerator


@dataclass
class Turn:
    """Represents a speaker turn on the parliament floor."""

    speaker: str
    text: str
    audio_path: str | None = None


class ParliamentBus:
    """Async publish/subscribe bus for :class:`Turn` messages."""

    def __init__(self) -> None:
        self._queues: list[asyncio.Queue[Turn]] = []
        self._lock = asyncio.Lock()

    async def publish(self, turn: Turn) -> None:
        """Publish ``turn`` to all subscribers."""
        async with self._lock:
            queues = list(self._queues)
        for q in queues:
            q.put_nowait(turn)

    async def subscribe(self) -> AsyncGenerator[Turn, None]:
        """Yield turns as they arrive until the consumer stops."""
        q: asyncio.Queue[Turn] = asyncio.Queue()
        async with self._lock:
            self._queues.append(q)
        try:
            while True:
                yield await q.get()
        finally:
            async with self._lock:
                self._queues.remove(q)
