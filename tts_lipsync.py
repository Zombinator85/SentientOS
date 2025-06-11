import json
from pathlib import Path
from typing import Dict, List, TypedDict

from sentientos.privilege import require_admin_banner, require_lumos_approval


class Viseme(TypedDict):
    time: float
    viseme: str
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
try:
    import pyttsx3
except Exception:  # pragma: no cover - optional
    pyttsx3 = None


def _simple_visemes(text: str) -> Dict[str, List[Viseme]]:
    visemes: List[Viseme] = []
    t = 0.0
    for word in text.split():
        char = word[0].lower()
        if char in "aei":
            vis = "A"
        elif char in "ou":
            vis = "O"
        else:
            vis = "neutral"
        visemes.append({"time": t, "viseme": vis})
        t += 0.2
    return {"visemes": visemes}


def synthesize(text: str, out_prefix: str = "speech") -> Dict[str, str]:
    audio_path = Path(f"{out_prefix}.wav")
    viseme_path = Path(f"{out_prefix}.json")
    if pyttsx3 is None:
        raise RuntimeError("pyttsx3 not available")
    engine = pyttsx3.init()
    engine.save_to_file(text, str(audio_path))
    engine.runAndWait()
    visemes = _simple_visemes(text)
    viseme_path.write_text(json.dumps(visemes, indent=2), encoding="utf-8")
    return {"audio": str(audio_path), "visemes": str(viseme_path)}


if __name__ == "__main__":  # pragma: no cover - manual
    import sys
    txt = " ".join(sys.argv[1:]) or "Hello"
    print(synthesize(txt))
