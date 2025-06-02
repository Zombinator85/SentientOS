from __future__ import annotations
from logging_config import get_log_path

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from admin_utils import require_admin_banner

try:  # pragma: no cover - optional Blender dependency
    import bpy  # type: ignore
except Exception:  # pragma: no cover - environment may lack Blender
    bpy = None  # type: ignore

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_PATH = get_log_path("avatar_mood_animation.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_change(avatar: str, mood: str, info: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "mood": mood,
        "info": info,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def update_avatar(avatar: str, mood: str) -> dict[str, Any]:
    """Apply mood adjustments to the avatar file if possible."""
    info: dict[str, Any] = {}
    if bpy is not None:
        try:
            bpy.ops.wm.open_mainfile(filepath=avatar)
            obj = getattr(bpy.context, "object", None)
            if obj is not None:
                setattr(obj, "applied_mood", mood)
                info["object"] = obj.name
            bpy.ops.wm.save_as_mainfile(filepath=avatar)
        except Exception as exc:  # pragma: no cover - Blender errors vary
            info["error"] = str(exc)
    else:
        info["note"] = "mood drift placeholder"
    return log_change(avatar, mood, info)


def main() -> None:
    require_admin_banner()
    import argparse

    ap = argparse.ArgumentParser(description="Mood evolving avatar animator")
    ap.add_argument("avatar")
    ap.add_argument("mood")
    args = ap.parse_args()
    entry = update_avatar(args.avatar, args.mood)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
