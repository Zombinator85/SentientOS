from __future__ import annotations
from logging_config import get_log_path

from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Avatar Federation Festival Coordinator."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_federation_festival.jsonl", "AVATAR_FEDERATION_FESTIVAL_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def schedule_festival(name: str, avatars: List[str], note: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "name": name,
        "avatars": avatars,
        "note": note,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_festivals() -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def generate_lorebook(entry: Dict[str, str], html: bool = False) -> str:
    avatars = ", ".join(entry.get("avatars", []))
    md = (
        f"# Federation Festival {entry['name']}\n"
        f"**Participants:** {avatars}\n\n"
        f"**Note:** {entry['note']}\n"
    )
    if not html:
        return md
    return md.replace("\n", "<br>\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Federation Festival Coordinator")
    sub = ap.add_subparsers(dest="cmd")

    sc = sub.add_parser("schedule", help="Schedule a federation festival")
    sc.add_argument("name")
    sc.add_argument("avatars")
    sc.add_argument("--note", default="")
    sc.set_defaults(func=lambda a: print(json.dumps(schedule_festival(a.name, [v.strip() for v in a.avatars.split(',') if v.strip()], a.note), indent=2)))

    ls = sub.add_parser("list", help="List festivals")
    ls.set_defaults(func=lambda a: print(json.dumps(list_festivals(), indent=2)))

    lb = sub.add_parser("lorebook", help="Generate lorebook for latest festival")
    lb.add_argument("--html", action="store_true")
    lb.set_defaults(func=lambda a: print(generate_lorebook(list_festivals()[-1], html=a.html)) if list_festivals() else print("No festivals logged"))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
