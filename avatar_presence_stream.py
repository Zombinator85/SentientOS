from __future__ import annotations
from logging_config import get_log_path

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sentientos.privilege import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("avatar_presence_stream.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def broadcast(event: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        **event,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Real-time avatar presence stream")
    ap.add_argument("event", help="JSON event data")
    args = ap.parse_args()
    try:
        data = json.loads(args.event)
    except Exception:
        data = {"raw": args.event}
    entry = broadcast(data)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
