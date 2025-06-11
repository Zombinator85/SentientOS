from __future__ import annotations
from logging_config import get_log_path

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sentientos.privilege import require_admin_banner, require_lumos_approval

try:  # pragma: no cover - optional Blender dependency
    import bpy  # type: ignore  # Blender API lacks stubs
except Exception:  # pragma: no cover - environment may lack Blender
    bpy = None  # type: ignore  # fallback when Blender unavailable

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("avatar_pose_log.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_pose(avatar: str, pose: str, context: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "pose": pose,
        "context": context,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def set_pose(avatar: str, pose: str) -> dict[str, Any]:
    """Set the avatar rig to the requested pose."""
    context: dict[str, Any] = {}
    if bpy is not None:
        try:
            bpy.ops.wm.open_mainfile(filepath=avatar)
            obj = getattr(bpy.context, "object", None)
            if obj is not None:
                setattr(obj, "pose_marker", pose)
                context["rig"] = obj.name
            bpy.ops.wm.save_as_mainfile(filepath=avatar)
        except Exception as exc:  # pragma: no cover - Blender errors vary
            context["error"] = str(exc)
    else:
        context["note"] = "pose placeholder"
    return log_pose(avatar, pose, context)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Avatar ritual pose engine")
    ap.add_argument("avatar")
    ap.add_argument("pose")
    args = ap.parse_args()
    entry = set_pose(args.avatar, args.pose)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
