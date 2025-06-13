"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import asyncio
from dataclasses import dataclass
from queue import SimpleQueue
from typing import Awaitable, Callable, Dict, List, Optional
import random

import emotion_fallback


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


_agent_emotion_map: Dict[str, Callable[[], str]] = {}
_resolve_rng: random.Random = random.Random(0)


def resolve_emotion(agent: str, profile: str) -> Optional[str]:
    """Return chosen emotion or fallback tone for ``agent`` and ``profile``."""
    fn = _agent_emotion_map.get(agent)
    chosen = fn() if fn is not None else None
    if chosen:
        return chosen
    weights = emotion_fallback.get_fallback_emotion_weights(profile)
    return _pick_emotion(weights, _resolve_rng)


async def parliament(
    prompt: str,
    chain: List[str],
    profile: str,
    agent_emotion_map: Optional[Dict[str, Callable[[], str]]] = None,
    rng: Optional[random.Random] = None,
) -> str:
    """Run a model chain publishing each turn with optional emotion."""
    global _agent_emotion_map, _resolve_rng
    _resolve_rng = rng or random.Random(0)
    _agent_emotion_map = agent_emotion_map or {}
    message = prompt
    for model in chain:
        reply = await _call_model(model, message)
        emotion = resolve_emotion(model, profile)
        parliament_bus.put(
            Turn(model=model, message=message, reply=reply, emotion=emotion),
        )
        message = reply
    return message
