from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import neos_bridge as nb
import presence_ledger as pl

LOG_PATH = Path(os.getenv("NEOS_FEDERATION_LOG", "logs/neos_federation.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def broadcast(event: str, note: str) -> dict:
    nb.send_message("federation", f"{event}: {note}")
    entry = {"timestamp": datetime.utcnow().isoformat(), "event": event, "note": note}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    pl.log("federation", event, note)
    return entry


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Cross-World Federation Sync")
    ap.add_argument("event")
    ap.add_argument("note")
    args = ap.parse_args()
    entry = broadcast(args.event, args.note)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
