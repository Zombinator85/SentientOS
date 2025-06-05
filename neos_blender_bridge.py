from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

LOG_PATH = get_log_path("neos_blender_bridge.jsonl", "NEOS_BLENDER_BRIDGE_LOG")
BLENDER_DIR = Path(os.getenv("NEOS_BLENDER_EXPORT_DIR", "blender_exports"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
BLENDER_DIR.mkdir(parents=True, exist_ok=True)

try:
    import bpy  # type: ignore
except Exception:  # pragma: no cover - environment may lack Blender
    bpy = None  # type: ignore


def export_cube(name: str) -> Path:
    if bpy is None:
        raise RuntimeError("Blender bpy module not available")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(size=1)
    obj = bpy.context.object
    obj.name = name
    out_path = BLENDER_DIR / f"{name}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out_path))
    return out_path


def log_session(asset: str, path: Path) -> dict:
    entry = {"timestamp": datetime.utcnow().isoformat(), "asset": asset, "path": str(path)}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR On-the-Fly Blender Bridge")
    ap.add_argument("asset")
    args = ap.parse_args()

    if bpy is None:
        print("bpy module not available. Run within Blender.")
        return
    out = export_cube(args.asset)
    entry = log_session(args.asset, out)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
