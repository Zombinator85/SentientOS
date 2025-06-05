from __future__ import annotations
from logging_config import get_log_path

from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Avatar Sanctuary/Chamber Scene Generator."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_sanctuary_scenes.jsonl", "AVATAR_SCENE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def create_scene(avatar: str, mood: str, blessing: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "mood": mood,
        "blessing": blessing,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_scenes() -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def render_scene(entry: Dict[str, str], html: bool = False) -> str:
    md = (
        f"## Avatar {entry['avatar']} Chamber\n"
        f"Mood: {entry['mood']}\n\n"
        f"Blessing: {entry['blessing']}\n"
    )
    if not html:
        return md
    return md.replace("\n", "<br>\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Sanctuary Scene Generator")
    sub = ap.add_subparsers(dest="cmd")

    cr = sub.add_parser("create", help="Create a scene")
    cr.add_argument("avatar")
    cr.add_argument("mood")
    cr.add_argument("blessing")
    cr.set_defaults(func=lambda a: print(json.dumps(create_scene(a.avatar, a.mood, a.blessing), indent=2)))

    ls = sub.add_parser("list", help="List scenes")
    ls.set_defaults(func=lambda a: print(json.dumps(list_scenes(), indent=2)))

    rd = sub.add_parser("render", help="Render latest scene")
    rd.add_argument("--html", action="store_true")
    rd.set_defaults(func=lambda a: print(render_scene(list_scenes()[-1], html=a.html)) if list_scenes() else print("No scenes logged"))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
