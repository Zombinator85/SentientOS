from __future__ import annotations
from logging_config import get_log_path

from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
"""Avatar Self-Portrait & Creative Gift Engine.

Avatars periodically generate self-portraits or creative artifacts (image, poem,
song). Each gift is logged as a blessing and can be viewed or rated from a
simple CLI gallery.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict

GIFT_DIR = Path(os.getenv("AVATAR_GIFT_DIR", "gifts"))
LOG_PATH = get_log_path("avatar_gifts.jsonl", "AVATAR_GIFT_LOG")
GIFT_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_gift(avatar: str, description: str, path: Path) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "description": description,
        "artifact": str(path),
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def create_gift(avatar: str, mood: str) -> Dict[str, str]:
    """Placeholder generation of a creative artifact."""
    filename = f"{avatar}_{int(datetime.utcnow().timestamp())}.txt"
    path = GIFT_DIR / filename
    path.write_text(f"Self portrait of {avatar} in mood {mood}", encoding="utf-8")
    return log_gift(avatar, f"Self portrait in mood {mood}", path)


def list_gifts() -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Creative Gift Engine")
    sub = ap.add_subparsers(dest="cmd")

    cg = sub.add_parser("create", help="Create a new gift")
    cg.add_argument("avatar")
    cg.add_argument("--mood", default="neutral")
    cg.set_defaults(
        func=lambda a: print(json.dumps(create_gift(a.avatar, a.mood), indent=2))
    )

    ls = sub.add_parser("list", help="List gifts")
    ls.set_defaults(func=lambda a: print(json.dumps(list_gifts(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
