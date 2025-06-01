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
    entry = tf.invite(peer, email=email, message=message)
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
    sub = ap.add_subparsers(dest="cmd")

    inv = sub.add_parser("invite", help="Invite a peer to federate")
    inv.add_argument("peer")
    inv.add_argument("--email")
    inv.add_argument("--message")
    inv.set_defaults(func=cmd_invite)

    args = ap.parse_args()
    print_banner()

    if args.ledger:
        ledger.print_summary()
        print_closing()
        return

    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()
    print_closing()


if __name__ == "__main__":
    main()
