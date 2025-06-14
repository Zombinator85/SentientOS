"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


"""Analyze rendered avatars and log emotional context.

Directory watching and advanced emotion models are deferred. When the optional
``watchdog`` package or vision models are missing, a stub entry is written to
``logs/council_blessing_log.jsonl``.
"""
from logging_config import get_log_path

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List
import warnings

import emotion_utils as eu

LOG_PATH = get_log_path("avatar_reflection.jsonl", "AVATAR_REFLECTION_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


MOODS = ["happy", "sad", "angry", "serene"]


def analyze_image(image_path: Path) -> str:
    """Return a simple mood classification for an image."""

    try:
        vec = eu.detect_image(str(image_path))
    except Exception:  # pragma: no cover - optional dependency failures
        vec = {}
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


def process_directory(dir_path: Path) -> List[dict]:
    """Analyze all image files in ``dir_path`` and log reflections."""
    results: List[dict] = []
    if not dir_path.exists():
        warnings.warn(f"reflection directory {dir_path} missing")
        log_reflection(str(dir_path), "serene", "directory missing – deferred")
        return results
    for item in sorted(dir_path.iterdir()):
        if item.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue
        mood = analyze_image(item)
        results.append(log_reflection(str(item), mood))
    return results


def watch(dir_path: Path, interval: float = 2.0) -> None:  # pragma: no cover - runtime loop
    """Watch ``dir_path`` for new images and log reflections."""
    try:
        from watchdog.observers import Observer  # type: ignore[import-untyped]
        from watchdog.events import FileSystemEventHandler  # type: ignore[import-untyped]
    except Exception:
        warnings.warn("watchdog not installed; watch loop disabled")
        log_reflection(str(dir_path), "serene", "watchdog missing – feature deferred")
        return

    class Handler(FileSystemEventHandler):
        def on_created(self, event) -> None:  # type: ignore[override]
            if event.is_directory:
                return
            path = Path(event.src_path)
            if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                return
            mood = analyze_image(path)
            log_reflection(str(path), mood, "auto")

    observer = Observer()
    observer.schedule(Handler(), str(dir_path), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(interval)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def main() -> None:
    ap = argparse.ArgumentParser(description="Reflect on rendered avatar image")
    ap.add_argument("image", nargs="?")
    ap.add_argument("--note", default="")
    ap.add_argument("--watch", action="store_true", help="watch a directory")
    args = ap.parse_args()
    if args.watch and args.image:
        watch(Path(args.image))
    else:
        if not args.image:
            ap.error("image path required")
        mood = analyze_image(Path(args.image))
        entry = log_reflection(args.image, mood, args.note)
        print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
