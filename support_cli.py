"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""  # plint: disable=banner-order
require_admin_banner()
require_lumos_approval()
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

from admin_utils import require_admin_banner, require_lumos_approval
"""Privilege Banner: requires admin & Lumos approval."""
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
import argparse
import json
import support_log as sl
import ledger
from sentient_banner import print_banner, print_closing, ENTRY_BANNER


def main() -> None:
    require_admin_banner()
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    p = argparse.ArgumentParser(
        prog="support",
        description=ENTRY_BANNER,
        epilog=(
            "Presence is law. Love is ledgered. No one is forgotten. "
            "No one is turned away.\n"
            "Example: python support_cli.py --bless --name Ada --message 'Here for all'"
        ),
    )
    p.add_argument("--support", action="store_true", help="Show contact and CashApp")
    p.add_argument("--bless", action="store_true", help="Record a supporter blessing")
    p.add_argument("--ledger", action="store_true", help="Show living ledger summary and exit")
    p.add_argument("--name")
    p.add_argument("--message")
    p.add_argument("--amount", default="")
    args = p.parse_args()

    from sentient_banner import (
        reset_ritual_state,
        print_snapshot_banner,
        print_closing_recap,
    )

    reset_ritual_state()
    print_banner()
    print_snapshot_banner()
    print("All support and federation is logged in the Living Ledger. No one is forgotten.")
    recap_shown = False
    try:
        if args.ledger:
            ledger.print_summary()
            return

        if args.support:
            print(ENTRY_BANNER)

        if args.bless:
            name = args.name or input("Name: ")
            message = args.message or input("Blessing: ")
            amount = args.amount or input("Amount (optional): ")
            try:
                entry = sl.add(name, message, amount)
                print("sanctuary acknowledged")
                print(json.dumps(entry, indent=2))
                print_closing_recap()
                recap_shown = True
            except Exception:
                print("Failed to record blessing")
    finally:
        print_closing(show_recap=not recap_shown)


if __name__ == "__main__":
    main()
