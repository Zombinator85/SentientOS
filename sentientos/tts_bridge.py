"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Optional text-to-speech bridge with graceful fallbacks."""

import asyncio
import json
import logging
import os
import sys
import warnings
from typing import Any

logger = logging.getLogger(__name__)

ENABLE_TTS = os.getenv("ENABLE_TTS", "true").lower() == "true"
ENGINE_TYPE = os.getenv("TTS_ENGINE", "pyttsx3")

try:
    if ENGINE_TYPE == "edge-tts":
        from edge_tts import Communicate as EdgeCommunicate
        _edge_available = True
    else:
        EdgeCommunicate = None
        _edge_available = False
except Exception:
    EdgeCommunicate = None
    _edge_available = False

try:
    import pyttsx3
    _pyttsx3_available = True
except Exception:
    pyttsx3 = None
    _pyttsx3_available = False


def is_tts_available() -> bool:
    """Return True if a TTS engine is available."""
    return _pyttsx3_available or _edge_available


async def say(text: str, voice: str = "en-US-GuyNeural") -> None:
    """Speak ``text`` asynchronously if possible."""
    if not ENABLE_TTS or not is_tts_available():
        logger.warning(json.dumps({"event_type": "tts_error", "emotion": "frustrated"}))
        print(text)
        return

    if ENGINE_TYPE == "edge-tts" and _edge_available and EdgeCommunicate is not None:
        try:
            comm = EdgeCommunicate(text=text, voice=voice)
            await comm.save("/tmp/tts_output.mp3")
        except Exception as exc:
            logger.error("[TTS error] %s", exc)
    elif ENGINE_TYPE == "pyttsx3" and _pyttsx3_available and pyttsx3 is not None:
        try:
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:
            logger.error("[TTS error] %s", exc)
    else:
        warnings.warn("[TTS disabled] no compatible engine")
        print(text)


def say_sync(text: str, voice: str = "en-US-GuyNeural") -> None:
    """Synchronous wrapper for :func:`say`."""
    asyncio.run(say(text, voice=voice))
