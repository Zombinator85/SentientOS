from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import emotion_utils as eu
from PIL import Image, ImageStat
from admin_utils import require_admin_banner, require_lumos_approval

LOG_PATH = get_log_path("avatar_reflection.jsonl", "AVATAR_REFLECTION_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


MOODS = ["happy", "sad", "angry", "serene"]


def analyze_image(image_path: Path) -> str:
    """Return a simple mood classification for an image."""

    try:
        img = Image.open(image_path).convert("RGB")
    except Exception:
        return "serene"
    stat = ImageStat.Stat(img)
    r, g, b = stat.mean
    if r > g and r > b:
        return "angry"
    if b > r and b > g:
        return "sad"
    if g > r and g > b:
        return "happy"
    return "serene"


def log_reflection(image: str, mood: str, note: str = "") -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "image": image,
        "mood": mood,
        "note": note,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Reflect on rendered avatar image")
    ap.add_argument("image")
    ap.add_argument("--note", default="")
    args = ap.parse_args()
    mood = analyze_image(Path(args.image))
    entry = log_reflection(args.image, mood, args.note)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
