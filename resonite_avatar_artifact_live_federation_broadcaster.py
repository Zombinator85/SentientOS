from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from sentientos.privilege import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("resonite_live_broadcast.jsonl", "RESONITE_LIVE_BROADCAST_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_broadcast(action: str, artifact: str, peer: str) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "artifact": artifact,
        "peer": peer,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def broadcast(artifact: str, peer: str) -> None:
    require_admin_banner()
    log_broadcast("broadcast", artifact, peer)
    print(json.dumps({"artifact": artifact, "peer": peer}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Avatar/Artifact live federation broadcaster")
    parser.add_argument("artifact")
    parser.add_argument("peer")
    args = parser.parse_args()
    broadcast(args.artifact, args.peer)


if __name__ == "__main__":
    main()
