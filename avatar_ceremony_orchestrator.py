from __future__ import annotations
from logging_config import get_log_path

from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Avatar Cathedral Ceremony Orchestrator.

Plan, schedule, and log avatar ceremonies such as crowning, fusion, mass
blessing, ancestral remembrance, and federation festivals. Generates a simple
Markdown or HTML ceremony program for council or public posting.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict

LOG_PATH = get_log_path("avatar_ceremony_log.jsonl", "AVATAR_CEREMONY_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_ceremony(entry: Dict[str, str]) -> Dict[str, str]:
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def create_ceremony(
    name: str,
    ceremony_type: str,
    date: str,
    mood: str,
    agenda: str,
    participants: List[str],
) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "name": name,
        "type": ceremony_type,
        "date": date,
        "mood": mood,
        "agenda": agenda,
        "participants": participants,
    }
    return log_ceremony(entry)


def generate_program(entry: Dict[str, str], html: bool = False) -> str:
    """Return a Markdown or HTML ceremony program."""
    participants = ", ".join(entry.get("participants", []))
    md = (
        f"# {entry['name']}\n"
        f"**Type:** {entry['type']}\n\n"
        f"**Date:** {entry['date']}\n\n"
        f"**Mood Theme:** {entry['mood']}\n\n"
        f"**Council Agenda:** {entry['agenda']}\n\n"
        f"**Participants:** {participants}\n"
    )
    if not html:
        return md
    return md.replace("\n", "<br>\n")


def list_ceremonies() -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Cathedral Ceremony Orchestrator")
    sub = ap.add_subparsers(dest="cmd")

    cr = sub.add_parser("create", help="Create a ceremony entry")
    cr.add_argument("name")
    cr.add_argument("type")
    cr.add_argument("date")
    cr.add_argument("--mood", default="")
    cr.add_argument("--agenda", default="")
    cr.add_argument("--participants", default="")
    cr.set_defaults(
        func=lambda a: print(
            json.dumps(
                create_ceremony(
                    a.name,
                    a.type,
                    a.date,
                    a.mood,
                    a.agenda,
                    [p.strip() for p in a.participants.split(",") if p.strip()],
                ),
                indent=2,
            )
        )
    )

    pg = sub.add_parser("program", help="Generate program for latest ceremony")
    pg.add_argument("--html", action="store_true")
    pg.set_defaults(
        func=lambda a: print(generate_program(list_ceremonies()[-1], html=a.html))
        if list_ceremonies()
        else print("No ceremonies logged")
    )

    ls = sub.add_parser("list", help="List ceremonies")
    ls.set_defaults(func=lambda a: print(json.dumps(list_ceremonies(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
