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

LOG_PATH = get_log_path("neos_avatar_relics.jsonl", "NEOS_RELIC_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def create_relic(avatar: str, relic_type: str) -> Dict[str, str]:
    """Create an avatar relic entry."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "type": relic_type,
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
    ap = argparse.ArgumentParser(description="NeosVR Avatar Relic Generator")
    sub = ap.add_subparsers(dest="cmd")

    cr = sub.add_parser("create", help="Create relic")
    cr.add_argument("avatar")
    cr.add_argument("type")
    cr.set_defaults(func=lambda a: print(json.dumps(create_relic(a.avatar, a.type), indent=2)))

    hist = sub.add_parser("history", help="Show relic history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
