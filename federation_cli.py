import argparse
import json
import sys
from sentient_banner import (
    print_banner,
    print_closing,
    ENTRY_BANNER,
    reset_ritual_state,
    print_snapshot_banner,
    print_closing_recap,
)
from admin_utils import require_admin_banner
import treasury_federation as tf
import ledger
import mood_wall
from pathlib import Path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""


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


def cmd_playlist(args: argparse.Namespace) -> None:
    entries = ledger.playlist_by_mood(args.mood, args.limit)
    log = ledger.playlist_log(entries, args.mood, args.user, "local")
    print(json.dumps(log, indent=2))


def cmd_sync_wall(args: argparse.Namespace) -> None:
    count = mood_wall.sync_wall(Path(args.path))
    print(json.dumps({"synced": count}))


def cmd_global_playlist(args: argparse.Namespace) -> None:
    local = ledger.playlist_by_mood(args.mood, args.limit)
    peer = []
    if args.peer and Path(args.peer).exists():
        peer = mood_wall.load_wall(args.limit)
    log = ledger.playlist_log(local + peer, args.mood, args.user, "global")
    print(json.dumps(log, indent=2))


def main() -> None:
    require_admin_banner()
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
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

    plst = sub.add_parser("playlist", help="Get playlist by mood")
    plst.add_argument("mood")
    plst.add_argument("--limit", type=int, default=10)
    plst.add_argument("--user", default="anon")
    plst.set_defaults(func=cmd_playlist)

    syncw = sub.add_parser("sync_wall", help="Sync mood wall events from path")
    syncw.add_argument("path")
    syncw.set_defaults(func=cmd_sync_wall)

    gpl = sub.add_parser("global_playlist", help="Merge playlist from peer")
    gpl.add_argument("mood")
    gpl.add_argument("--peer")
    gpl.add_argument("--limit", type=int, default=10)
    gpl.add_argument("--user", default="anon")
    gpl.set_defaults(func=cmd_global_playlist)

    args = ap.parse_args()
    reset_ritual_state()
    print_banner()
    print_snapshot_banner()

    recap_shown = False
    try:
        if args.ledger_summary:
            print_snapshot_banner()
            return

        if args.ledger:
            ledger.print_summary()
            return

        if hasattr(args, "func"):
            args.func(args)
            print_closing_recap()
            recap_shown = True
        else:
            ap.print_help()
    finally:
        print_closing(show_recap=not recap_shown)


if __name__ == "__main__":
    main()
