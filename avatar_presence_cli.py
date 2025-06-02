"""Record avatar invocation and presence blessing.

This CLI logs each time an avatar is invoked for a specific reason.
A presence affirmation is stored with a blessing message.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_PATH = Path(os.getenv("AVATAR_PRESENCE_LOG", "logs/avatar_presence.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_invocation(path: str, reason: str, mode: str = "visual") -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": path,
        "mode": mode,
        "reason": reason,
        "blessing": f"Avatar crowned for {reason}",
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Invoke avatar with blessing")
    ap.add_argument("avatar")
    ap.add_argument("reason")
    ap.add_argument("--mode", default="visual")
    args = ap.parse_args()
    entry = log_invocation(args.avatar, args.reason, args.mode)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
