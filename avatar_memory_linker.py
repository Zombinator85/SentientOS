"""Avatar Memory Linker CLI

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.

Links avatar events (generation, invocation, federation) to moods and memory fragments.
Each link is recorded in a ritual ledger for later query.

Example:
    python avatar_memory_linker.py link avatar1 blend created --mood joy --memory 123
    python avatar_memory_linker.py list --term forgiveness
"""
from __future__ import annotations

from admin_utils import require_admin_banner

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_memory_link.jsonl", "AVATAR_MEMORY_LINK_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_link(
    avatar: str,
    event: str,
    mood: str = "",
    memory: str = "",
    blessing: str = "",
    confession: str = "",
) -> Dict[str, str]:
    """Record a link between an avatar event and memory fragments."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "event": event,
        "mood": mood,
        "memory": memory,
        "blessing": blessing,
        "confession": confession,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_links(term: str = "") -> List[Dict[str, str]]:
    """Return logged links optionally filtered by a search term."""
    if not LOG_PATH.exists():
        return []
    out = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if term and term not in line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Avatar memory linker")
    sub = ap.add_subparsers(dest="cmd")

    lk = sub.add_parser("link", help="Link an avatar event to memory")
    lk.add_argument("avatar")
    lk.add_argument("event")
    lk.add_argument("--mood", default="")
    lk.add_argument("--memory", default="")
    lk.add_argument("--blessing", default="")
    lk.add_argument("--confession", default="")
    lk.set_defaults(
        func=lambda a: print(
            json.dumps(
                log_link(
                    a.avatar,
                    a.event,
                    mood=a.mood,
                    memory=a.memory,
                    blessing=a.blessing,
                    confession=a.confession,
                ),
                indent=2,
            )
        )
    )

    ls = sub.add_parser("list", help="List links")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_links(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
