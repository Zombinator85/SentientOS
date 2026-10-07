from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details.

avatar_gallery_cli.py — CLI tool to display the avatar invocation gallery.

Usage:
    python -m scripts.avatar_gallery_cli --help
"""
from logging_config import resolve_log_path
import argparse
import json
import os
from pathlib import Path
PRESENCE_LOG = resolve_log_path("avatar_presence.jsonl", "AVATAR_PRESENCE_LOG")


def list_invocations(filter_reason: str = "") -> list[dict]:
    require_admin_banner()
    require_lumos_approval()
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
    ap = argparse.ArgumentParser(description="Avatar gallery viewer")
    ap.add_argument("--reason", default="", help="Filter by invocation reason")
    args = ap.parse_args()
    for e in list_invocations(args.reason):
        print(json.dumps(e, indent=2))


if __name__ == "__main__":
    main()
