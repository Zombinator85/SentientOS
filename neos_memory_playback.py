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

import memory_manager as mm
import neos_bridge as nb

LOG_PATH = get_log_path("neos_memory_playback.jsonl", "NEOS_PLAYBACK_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def playback(fragment: str) -> dict:
    nb.send_message("playback", fragment)
    entry = {"timestamp": datetime.utcnow().isoformat(), "fragment": fragment}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    mm.append_memory(f"Playback: {fragment}", tags=["vr", "playback"], source="neos")
    return entry


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Ritual Memory Playback")
    ap.add_argument("fragment", help="Text to replay in VR")
    args = ap.parse_args()
    entry = playback(args.fragment)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
