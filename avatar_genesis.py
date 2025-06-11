from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Avatar genesis script using Blender's Python API.

This module provides a CLI tool to procedurally generate an avatar
based on a mood. The avatar is saved to a .blend file and a ritual
blessing entry is logged. For complex modeling/rigging this example
uses very simple geometry.
"""
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

LOG_PATH = get_log_path("avatar_genesis.jsonl", "AVATAR_GENESIS_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


try:
    import bpy  # type: ignore  # Blender API lacks stubs
except Exception:  # pragma: no cover - environment may lack Blender
    bpy = None  # type: ignore  # Blender unavailable


BLEND_DIR = Path(os.getenv("AVATAR_DIR", "avatars"))
BLEND_DIR.mkdir(parents=True, exist_ok=True)


def _log_blessing(mood: str, path: Path) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "mood": mood,
        "path": str(path),
        "blessing": "Avatar crowned for genesis",
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def generate_avatar(mood: str, out_path: Path) -> Path:
    """Generate a simple avatar with Blender.

    Parameters
    ----------
    mood:
        Mood name used to influence avatar style.
    out_path:
        Path where the .blend file should be saved.
    """
    if bpy is None:
        raise RuntimeError("Blender bpy module not available")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1)
    obj = bpy.context.object
    obj.name = f"avatar_{mood}"

    m = mood.lower()
    mat = bpy.data.materials.new(name=f"mat_{m}")
    if "happy" in m or "joy" in m:
        obj.scale = (1.2, 1.2, 1.2)
        mat.diffuse_color = (1.0, 0.9, 0.3, 1)
    elif "sad" in m or "melanch" in m:
        obj.scale = (0.8, 0.8, 0.8)
        mat.diffuse_color = (0.2, 0.2, 1.0, 1)
    else:
        mat.diffuse_color = (0.8, 0.8, 0.8, 1)
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    bpy.ops.wm.save_as_mainfile(filepath=str(out_path))
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate ritual avatar")
    ap.add_argument("mood", help="Mood for the avatar")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    out = Path(args.out or BLEND_DIR / f"{args.mood}.blend")
    if bpy is None:
        print("bpy module not available. Run within Blender.")
        return
    generate_avatar(args.mood, out)
    entry = _log_blessing(args.mood, out)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
