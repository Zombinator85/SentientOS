"""Analyze rendered avatars and log emotional context."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import emotion_utils as eu

LOG_PATH = Path(os.getenv("AVATAR_REFLECTION_LOG", "logs/avatar_reflection.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


MOODS = ["happy", "sad", "angry", "serene"]


def analyze_image(image_path: Path) -> str:
    """Return a simple mood classification for an image."""

    vec = eu.detect_image(str(image_path))
    if vec.get("Joy", 0.0) > 0:
        return "happy"
    if vec.get("Sadness", 0.0) > 0:
        return "sad"
    if vec.get("Anger", 0.0) > 0:
        return "angry"
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
    ap = argparse.ArgumentParser(description="Reflect on rendered avatar image")
    ap.add_argument("image")
    ap.add_argument("--note", default="")
    args = ap.parse_args()
    mood = analyze_image(Path(args.image))
    entry = log_reflection(args.image, mood, args.note)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
