"""Federation Ritual Handshake Protocol

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from admin_utils import require_admin_banner

LOG_PATH = Path(os.getenv("FEDERATION_HANDSHAKE_LOG", "logs/federation_handshake.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def handshake(node: str, token: str, consent: bool) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "node": node,
        "token": token,
        "consent": consent,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def cli() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Federation handshake")
    ap.add_argument("node")
    ap.add_argument("token")
    ap.add_argument("--consent", action="store_true")
    args = ap.parse_args()
    entry = handshake(args.node, args.token, args.consent)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":  # pragma: no cover
    cli()
