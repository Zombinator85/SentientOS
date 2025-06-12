from __future__ import annotations

"""Optional text-to-speech bridge using edge-tts."""

import asyncio
import sys

try:
    from edge_tts import Communicate  # optional HTTP client
except Exception:
    Communicate = None


async def say(text: str, voice: str = "en-US-GuyNeural") -> None:
    """Speak ``text`` asynchronously if edge-tts is available."""
    if Communicate is None:
        print("[TTS disabled] edge-tts is not installed.", file=sys.stderr)
        return
    try:
        comm = Communicate(text=text, voice=voice)
        await comm.save("/tmp/tts_output.mp3")
    except Exception as exc:
        print(f"[TTS error] {exc}", file=sys.stderr)


def say_sync(text: str, voice: str = "en-US-GuyNeural") -> None:
    """Synchronous wrapper for :func:`say`."""
    asyncio.run(say(text, voice=voice))
