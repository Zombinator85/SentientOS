"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import sys

from sentientos import tts_bridge


def main() -> None:
    """Invoke text-to-speech from the command line."""
    if os.getenv("ENABLE_TTS", "false").lower() != "true":
        print("TTS disabled. Set ENABLE_TTS=true to enable.")
        return
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.tts_cli 'Your message here'")
        return
    text = " ".join(sys.argv[1:])
    tts_bridge.say_sync(text)


if __name__ == "__main__":  # pragma: no cover - CLI invocation
    main()
