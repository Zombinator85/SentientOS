"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import asyncio
from dataclasses import dataclass
from queue import SimpleQueue
from typing import Awaitable, Callable, Dict, List


@dataclass
class Turn:
    """One exchange between a model and the parliament."""

    model: str
    message: str
    reply: str


# Global bus collecting all turns processed by ``parliament``
parliament_bus: "SimpleQueue[Turn]" = SimpleQueue()

# Registry of model wrapper functions
ModelFunc = Callable[[str], Awaitable[str]]
MODEL_REGISTRY: Dict[str, ModelFunc] = {}


def register_model(name: str, func: ModelFunc) -> None:
    """Register a model wrapper under ``name``."""
    MODEL_REGISTRY[name] = func


async def _call_model(model: str, message: str) -> str:
    fn = MODEL_REGISTRY.get(model)
    if fn is None:
        raise ValueError(f"Unknown model: {model}")
    return await fn(message)


async def parliament(prompt: str, chain: List[str], cycles: int = 1) -> str:
    """Run a model chain for a number of cycles publishing each turn."""
    message = prompt
    for _ in range(cycles):
        for model in chain:
            reply = await _call_model(model, message)
            parliament_bus.put(Turn(model=model, message=message, reply=reply))
            message = reply
    return message
