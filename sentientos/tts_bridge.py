"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
"""Optional text-to-speech bridge using edge-tts."""

import asyncio
import logging
import sys
import warnings
from typing import Any

logger = logging.getLogger(__name__)

try:
    from edge_tts import Communicate
except Exception:
    Communicate = None


async def say(text: str, voice: str = "en-US-GuyNeural") -> None:
    """Speak ``text`` asynchronously if edge-tts is available."""
    if Communicate is None:
        warnings.warn("[TTS disabled] edge-tts is not installed.")
        return
    try:
        comm = Communicate(text=text, voice=voice)
        await comm.save("/tmp/tts_output.mp3")
    except Exception as exc:
        logger.error("[TTS error] %s", exc)


def say_sync(text: str, voice: str = "en-US-GuyNeural") -> None:
    """Synchronous wrapper for :func:`say`."""
    asyncio.run(say(text, voice=voice))
