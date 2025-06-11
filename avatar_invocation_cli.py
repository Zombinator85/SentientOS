"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
require_admin_banner()
require_lumos_approval()
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path
import argparse
import json
from datetime import datetime
from pathlib import Path



LOG_PATH = get_log_path("avatar_invocation.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_invocation(line: str, mode: str, user: str = "") -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "line": line,
        "mode": mode,
        "user": user,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar ritual invocation")
    ap.add_argument("line")
    ap.add_argument("--mode", default="voice")
    ap.add_argument("--user", default="")
    ap.add_argument("--print-blessing", action="store_true")
    args = ap.parse_args()
    entry = log_invocation(args.line, args.mode, args.user)
    if args.print_blessing:
        print("Presence affirmed. Avatar blessed.")
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
