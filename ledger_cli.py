"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from logging_config import get_log_path
import argparse
import json
from pathlib import Path
import ledger
from sentient_banner import print_banner, print_closing, ENTRY_BANNER
from admin_utils import require_admin_banner, require_lumos_approval
import presence_ledger as pl
require_admin_banner()
require_lumos_approval()
SUPPORT_LOG = get_log_path("support_log.jsonl")
FED_LOG = get_log_path("federation_log.jsonl")


def cmd_open(args: argparse.Namespace) -> None:
    """Print all ledger entries in order."""
    for path in [SUPPORT_LOG, FED_LOG]:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                print(line)


def cmd_summary(args: argparse.Namespace) -> None:
    """Print a summary of ledger counts and recent entries."""
    sup = ledger.summarize_log(SUPPORT_LOG)
    fed = ledger.summarize_log(FED_LOG)
    priv = pl.recent_privilege_attempts()
    data = {
        'support_count': sup['count'],
        'federation_count': fed['count'],
        'support_recent': sup['recent'],
        'federation_recent': fed['recent'],
        'privilege_recent': priv,
    }
    print(json.dumps(data, indent=2))


def main() -> None:
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    ap = argparse.ArgumentParser(
        prog="ledger",
        description=ENTRY_BANNER,
        epilog=(
            "Presence is law. Love is ledgered. No one is forgotten. "
            "No one is turned away.\n"
            "Example: python ledger_cli.py --support --name Ada --message 'Blessing'"
        ),
    )
    ap.add_argument("--support", action="store_true", help="Record a supporter blessing")
    ap.add_argument("--summary", action="store_true", help="Show ledger summary and exit")
    ap.add_argument("--name")
    ap.add_argument("--message")
    ap.add_argument("--amount", default="")
    sub = ap.add_subparsers(dest="cmd")
    op = sub.add_parser("open", help="View all ledger entries")
    op.set_defaults(func=cmd_open)
    sm = sub.add_parser("summary", help="Show ledger summary")
    sm.set_defaults(func=cmd_summary)
    args = ap.parse_args()
    from sentient_banner import (
        reset_ritual_state,
        print_snapshot_banner,
        print_closing_recap,
    )

    reset_ritual_state()
    print_banner()
    print_snapshot_banner()

    recap_shown = False
    try:
        if args.support:
            name = args.name or input("Name: ")
            message = args.message or input("Message: ")
            amount = args.amount or input("Amount (optional): ")
            entry = ledger.log_support(name, message, amount)
            print(json.dumps(entry, indent=2))
            print_closing_recap()
            recap_shown = True
            if not args.cmd and not args.summary:
                return

        if args.summary and not args.cmd:
            cmd_summary(args)
            return

        if hasattr(args, "func"):
            args.func(args)
        else:
            ap.print_help()
    finally:
        print_closing(show_recap=not recap_shown)


if __name__ == '__main__':
    main()
