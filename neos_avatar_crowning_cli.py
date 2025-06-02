from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import presence_ledger as pl
import memory_manager as mm
import neos_bridge as nb

LOG_PATH = Path(os.getenv("NEOS_CROWN_LOG", "logs/neos_avatar_crowning.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
AGENTS_PATH = Path("AGENTS.md")


def crown_avatar(name: str) -> dict:
    banner = AGENTS_PATH.read_text(encoding="utf-8")
    nb.send_message("crowning", f"{name} crowned")
    pl.log(name, "crowned", "NeosVR avatar")
    mm.append_memory(f"{name} crowned as VR avatar", tags=["vr", "crown"], source="neos")
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": name,
        "banner_excerpt": banner.splitlines()[:5],
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Avatar Crowning Ceremony")
    ap.add_argument("avatar")
    args = ap.parse_args()
    entry = crown_avatar(args.avatar)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
