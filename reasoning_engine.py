"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import asyncio
from dataclasses import dataclass
from queue import SimpleQueue
from typing import Awaitable, Callable, Dict, List, Optional
import os
import random

import persona_config


@dataclass
class Turn:
    """One exchange between a model and the parliament."""

    model: str
    message: str
    reply: str
    emotion: Optional[str] = None


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


def _pick_emotion(weights: Dict[str, float], rng: random.Random) -> Optional[str]:
    total = sum(max(w, 0.0) for w in weights.values())
    if total <= 0:
        return None
    r = rng.random() * total
    upto = 0.0
    for emotion, weight in weights.items():
        w = max(weight, 0.0)
        upto += w
        if r <= upto:
            return emotion
    return None


async def parliament(
    prompt: str,
    chain: List[str],
    cycles: int = 1,
    *,
    persona: Optional[str] = None,
    persona_cfg: Optional[Dict[str, Dict[str, float]]] = None,
    rng: Optional[random.Random] = None,
) -> str:
    """Run a model chain publishing each turn with optional emotion."""
    rng = rng or random.Random(0)
    if persona_cfg is None:
        path = os.getenv("PERSONA_CONFIG_PATH", "profiles/default/persona_config.yaml")
        persona_cfg = persona_config.load_persona_config(path)
    message = prompt
    for _ in range(cycles):
        for model in chain:
            reply = await _call_model(model, message)
            emotion = None
            if persona and persona in persona_cfg:
                emotion = _pick_emotion(persona_cfg[persona], rng)
            parliament_bus.put(
                Turn(model=model, message=message, reply=reply, emotion=emotion)
            )
            message = reply
    return message
