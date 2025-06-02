from __future__ import annotations
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_avatar_lore.jsonl", "NEOS_AVATAR_LORE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def annotate_avatar(avatar: str, lore: str, note: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "lore": lore,
        "note": note,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry

def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out

def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Avatar Lore Annotator")
    sub = ap.add_subparsers(dest="cmd")

    an = sub.add_parser("annotate", help="Annotate avatar lore")
    an.add_argument("avatar")
    an.add_argument("lore")
    an.add_argument("--note", default="")
    an.set_defaults(func=lambda a: print(json.dumps(annotate_avatar(a.avatar, a.lore, a.note), indent=2)))

    hist = sub.add_parser("history", help="Show lore history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
