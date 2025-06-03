"""Simple CLI to view avatars and presence pulses."""

from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from pathlib import Path
from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

PRESENCE_LOG = get_log_path("avatar_presence.jsonl", "AVATAR_PRESENCE_LOG")


def list_invocations(filter_reason: str = "") -> list[dict]:
    if not PRESENCE_LOG.exists():
        return []
    entries = []
    for line in PRESENCE_LOG.read_text(encoding="utf-8").splitlines():
        data = json.loads(line)
        if filter_reason and data.get("reason") != filter_reason:
            continue
        entries.append(data)
    return entries


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Avatar gallery viewer")
    ap.add_argument("--reason", default="", help="Filter by invocation reason")
    args = ap.parse_args()
    for e in list_invocations(args.reason):
        print(json.dumps(e, indent=2))


if __name__ == "__main__":
    main()
