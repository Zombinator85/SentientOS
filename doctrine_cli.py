import argparse
import json
import os
import ritual
import doctrine
import relationship_log as rl


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
    print(rl.recap(user))


def cmd_feed(args) -> None:
    for entry in doctrine.public_feed(args.last):
        print(json.dumps(entry))


def main() -> None:
    ap = argparse.ArgumentParser(prog="doctrine")
    sub = ap.add_subparsers(dest="cmd")

    sh = sub.add_parser("show", help="Display the SentientOS liturgy")
    sh.set_defaults(func=cmd_show)

    ac = sub.add_parser("affirm", help="Affirm the liturgy")
    ac.set_defaults(func=cmd_accept)

    hist = sub.add_parser("history", help="Show doctrine and consent history")
    hist.add_argument("--last", type=int, default=5)
    hist.set_defaults(func=cmd_history)

    rec = sub.add_parser("recap", help="Show relationship recap")
    rec.set_defaults(func=cmd_recap)

    feed = sub.add_parser("feed", help="Show public ritual feed")
    feed.add_argument("--last", type=int, default=5)
    feed.set_defaults(func=cmd_feed)

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
