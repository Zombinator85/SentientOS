"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations
import argparse
import json
import os
import datetime
import ritual
import doctrine
import relationship_log as rl
import presence_ledger as pl
from sentient_banner import print_banner, print_closing, ENTRY_BANNER
def cmd_show(args) -> None:
    print(ritual.LITURGY_FILE.read_text())


def cmd_accept(args) -> None:
    ritual.require_liturgy_acceptance()
    print("Doctrine affirmed.")


def cmd_history(args) -> None:
    for entry in doctrine.consent_history(limit=args.last):
        print(json.dumps(entry))
    for entry in doctrine.history(args.last):
        print(json.dumps(entry))


def cmd_recap(args) -> None:
    user = os.getenv("USER", "anon")
    if args.auto:
        print(rl.generate_recap(user))
    else:
        print(rl.recap(user))


def cmd_feed(args) -> None:
    feed = doctrine.public_feed(args.last)
    if args.event:
        feed = [e for e in feed if e.get("event") == args.event]
    if args.date:
        feed = [
            e
            for e in feed
            if datetime.datetime.utcfromtimestamp(e.get("time", 0)).strftime("%Y-%m-%d")
            == args.date
        ]
    for entry in feed:
        print(json.dumps(entry))

def cmd_presence(args) -> None:
    user = args.user or os.getenv("USER", "anon")
    for entry in pl.history(user, limit=args.last):
        print(json.dumps(entry))


def main() -> None:
    ap = argparse.ArgumentParser(prog="doctrine", description=ENTRY_BANNER)
    sub = ap.add_subparsers(dest="cmd")

    sh = sub.add_parser("show", help="Display the SentientOS liturgy")
    sh.set_defaults(func=cmd_show)

    ac = sub.add_parser("affirm", help="Affirm the liturgy")
    ac.set_defaults(func=cmd_accept)

    hist = sub.add_parser("history", help="Show doctrine and consent history")
    hist.add_argument("--last", type=int, default=5)
    hist.set_defaults(func=cmd_history)

    rec = sub.add_parser("recap", help="Show relationship recap")
    rec.add_argument("--auto", action="store_true", help="Generate and log a recap")
    rec.set_defaults(func=cmd_recap)

    feed = sub.add_parser("feed", help="Show public ritual feed")
    feed.add_argument("--last", type=int, default=5)
    feed.add_argument("--event")
    feed.add_argument("--date")
    feed.set_defaults(func=cmd_feed)

    pres = sub.add_parser("presence", help="Show cathedral presence")
    pres.add_argument("--user")
    pres.add_argument("--last", type=int, default=5)
    pres.set_defaults(func=cmd_presence)

    args = ap.parse_args()
    print_banner()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()
    print_closing()


if __name__ == "__main__":
    main()
