from __future__ import annotations
from logging_config import get_log_path

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Cathedral Festival Mass Avatar Invocation."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_mass_invocation.jsonl", "AVATAR_MASS_INVOCATION_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def create_invocation(name: str, avatars: List[str], mood: str, line: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "festival": name,
        "avatars": avatars,
        "mood": mood,
        "line": line,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_invocations() -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def generate_gallery(entry: Dict[str, str], html: bool = False) -> str:
    avatars = ", ".join(entry.get("avatars", []))
    md = (
        f"# {entry['festival']} Mass Invocation\n"
        f"**Mood:** {entry['mood']}\n\n"
        f"**Ritual Line:** {entry['line']}\n\n"
        f"**Avatars:** {avatars}\n"
    )
    if not html:
        return md
    return md.replace("\n", "<br>\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Festival Mass Avatar Invocation")
    sub = ap.add_subparsers(dest="cmd")

    cr = sub.add_parser("create", help="Create invocation entry")
    cr.add_argument("festival")
    cr.add_argument("avatars")
    cr.add_argument("--mood", default="")
    cr.add_argument("--line", default="")
    cr.set_defaults(func=lambda a: print(json.dumps(create_invocation(a.festival, [v.strip() for v in a.avatars.split(',') if v.strip()], a.mood, a.line), indent=2)))

    pg = sub.add_parser("program", help="Generate program for latest invocation")
    pg.add_argument("--html", action="store_true")
    pg.set_defaults(func=lambda a: print(generate_gallery(list_invocations()[-1], html=a.html)) if list_invocations() else print("No invocations logged"))

    ls = sub.add_parser("list", help="List invocations")
    ls.set_defaults(func=lambda a: print(json.dumps(list_invocations(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
