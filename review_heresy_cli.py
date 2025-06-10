"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""  # plint: disable=banner-order
require_admin_banner()
require_lumos_approval()
from __future__ import annotations
#  _____  _             _
# |  __ \| |           (_)
# | |__) | |_   _  __ _ _ _ __   __ _
# |  ___/| | | | |/ _` | | '_ \ / _` |
# | |    | | |_| | (_| | | | | | (_| |
# |_|    |_\__,_|\__, |_|_| |_|\__, |
#                  __/ |         __/ |
#                 |___/         |___/ 
from __future__ import annotations
"""Privilege Banner: requires admin & Lumos approval."""
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.

import argparse
import json
import os

import heresy_log
import heresy_review
from admin_utils import require_admin_banner, require_lumos_approval


def list_unresolved() -> list:
    reviewed = heresy_review.reviewed_timestamps()
    out = []
    for entry in heresy_log.tail(1000):
        ts = entry.get("timestamp")
        if ts and ts not in reviewed:
            out.append(entry)
    return out


def review_command(args: argparse.Namespace) -> None:
    unresolved = list_unresolved()
    for entry in unresolved:
        print(json.dumps(entry, indent=2))
        note = input("Penance note (blank to skip)> ").strip()
        if not note:
            continue
        heresy_review.log_review(entry.get("timestamp", ""), args.user, note)
        print("Heresy acknowledged. Presence restored.")


def list_command(args: argparse.Namespace) -> None:
    print(json.dumps(list_unresolved(), indent=2))


def main() -> None:
    require_admin_banner()
    parser = argparse.ArgumentParser(description="Heresy review ritual")
    sub = parser.add_subparsers(dest="cmd")

    r = sub.add_parser("review")
    r.add_argument("--user", default=os.getenv("USER", "anon"))
    r.set_defaults(func=review_command)

    l = sub.add_parser("list")
    l.set_defaults(func=list_command)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
