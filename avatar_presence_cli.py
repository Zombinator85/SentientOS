"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
require_admin_banner()
require_lumos_approval()
from admin_utils import require_admin_banner, require_lumos_approval

from logging_config import get_log_path
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
"""Record avatar invocation and presence blessing.

This CLI logs each time an avatar is invoked for a specific reason.
A presence affirmation is stored with a blessing message.
"""


LOG_PATH = get_log_path("avatar_presence.jsonl", "AVATAR_PRESENCE_LOG")
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
    ap = argparse.ArgumentParser(description="Invoke avatar with blessing")
    ap.add_argument("avatar")
    ap.add_argument("reason")
    ap.add_argument("--mode", default="visual")
    args = ap.parse_args()
    entry = log_invocation(args.avatar, args.reason, args.mode)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
