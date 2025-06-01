import argparse
import json
import sys
from sentient_banner import print_banner, print_closing, ENTRY_BANNER
import treasury_federation as tf
import ledger


def cmd_invite(args: argparse.Namespace) -> None:
    peer = args.peer
    email = args.email or ""
    message = args.message or "Come be remembered"
    blessing = args.blessing or message
    name = args.name or peer
    entry = tf.invite(
        peer,
        email=email,
        message=message,
        blessing=blessing,
        supporter=name,
        affirm=args.affirm,
    )
    print(json.dumps(entry, indent=2))
    print("Example to share:\nYou are invited to join SentientOS: No one is turned away.")


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="federation",
        description=ENTRY_BANNER,
        epilog=(
            "Presence is law. Love is ledgered. No one is forgotten. "
            "No one is turned away.\n"
            "Example: python federation_cli.py invite https://ally --email you@e.com"
        ),
    )
    ap.add_argument("--ledger", action="store_true", help="Show living ledger summary and exit")
    ap.add_argument("--ledger-summary", action="store_true", help="Print ledger snapshot and exit")
    sub = ap.add_subparsers(dest="cmd")

    inv = sub.add_parser("invite", help="Invite a peer to federate")
    inv.add_argument("peer")
    inv.add_argument("--email")
    inv.add_argument("--message")
    inv.add_argument("--blessing")
    inv.add_argument("--name")
    inv.add_argument("--affirm", action="store_true", help="Pre-log a welcome affirmation")
    inv.set_defaults(func=cmd_invite)

    args = ap.parse_args()
    print_banner()
    ledger.print_snapshot_banner()

    if args.ledger_summary:
        ledger.print_snapshot_banner()
        print_closing()
        return

    if args.ledger:
        ledger.print_summary()
        print_closing()
        return

    if hasattr(args, "func"):
        args.func(args)
        ledger.print_recap(limit=2)
    else:
        ap.print_help()
    print_closing()


if __name__ == "__main__":
    main()
