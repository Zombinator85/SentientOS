from __future__ import annotations
from logging_config import get_log_path

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_PATH = get_log_path("avatar_lineage.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_event(avatar: str, event: str, parents: list[str] | None = None) -> dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "event": event,
        "parents": parents or [],
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def record_birth(name: str, parents: list[str]) -> dict[str, Any]:
    """Record lineage event."""
    return log_event(name, "birth", parents)


def main() -> None:
    require_admin_banner()
    import argparse

    ap = argparse.ArgumentParser(description="Avatar ancestry and lineage tracker")
    ap.add_argument("name")
    ap.add_argument("parents", nargs="*")
    args = ap.parse_args()
    entry = record_birth(args.name, args.parents)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
