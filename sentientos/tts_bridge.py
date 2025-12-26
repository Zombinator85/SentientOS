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

from sentientos.optional_deps import dependency_available, optional_import

logger = logging.getLogger(__name__)

ENABLE_TTS = os.getenv("ENABLE_TTS", "true").lower() == "true"
ENGINE_TYPE = os.getenv("TTS_ENGINE", "pyttsx3")

def is_tts_available() -> bool:
    """Return True if a TTS engine is available."""
    if ENGINE_TYPE == "edge-tts":
        return dependency_available("edge-tts")
    if ENGINE_TYPE == "pyttsx3":
        return dependency_available("pyttsx3")
    return dependency_available("edge-tts") or dependency_available("pyttsx3")


async def say(text: str, voice: str = "en-US-GuyNeural") -> None:
    """Speak ``text`` asynchronously if possible."""
    if not ENABLE_TTS or not is_tts_available():
        logger.warning(json.dumps({"event_type": "tts_error", "emotion": "frustrated"}))
        print(text)
        return

    if ENGINE_TYPE == "edge-tts":
        edge_tts = optional_import("edge-tts", feature="tts_bridge_edge")
        if edge_tts is None:
            logger.warning(json.dumps({"event_type": "tts_disabled", "engine": ENGINE_TYPE}))
            print(text)
            return
        try:
            comm = edge_tts.Communicate(text=text, voice=voice)
            await comm.save("/tmp/tts_output.mp3")
        except Exception as exc:
            logger.error("[TTS error] %s", exc)
    elif ENGINE_TYPE == "pyttsx3":
        pyttsx3 = optional_import("pyttsx3", feature="tts_bridge_pyttsx3")
        if pyttsx3 is None:
            logger.warning(json.dumps({"event_type": "tts_disabled", "engine": ENGINE_TYPE}))
            print(text)
            return
        try:
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:
            logger.error("[TTS error] %s", exc)
    else:
        logger.warning(json.dumps({"event_type": "tts_disabled", "engine": ENGINE_TYPE}))
        print(text)


def say_sync(text: str, voice: str = "en-US-GuyNeural") -> None:
    """Synchronous wrapper for :func:`say`."""
    asyncio.run(say(text, voice=voice))
