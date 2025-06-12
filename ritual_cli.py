"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
import argparse
import json
import os
from sentient_banner import print_banner, print_closing, ENTRY_BANNER
import attestation
import relationship_log as rl
def cmd_attest(args) -> None:
    user = args.user or os.getenv("USER", "anon")
    attestation.add(args.event, user, comment=args.comment or "", quote=args.quote or "")
    print("Attestation recorded")


def cmd_export(args) -> None:
    user = args.user
    events = rl.history(user if user != "all" else None, limit=100000)
    attest = attestation.history(None, limit=100000)
    data = {"events": events, "attestations": attest}
    print(json.dumps(data, indent=2))


def cmd_timeline(args) -> None:
    events = rl.history(args.user if args.user else None, limit=1000)
    for e in events:
        print(f"{e.get('time')} {e.get('event')} by {e.get('user')}")
        atts = attestation.history(e.get("id"), limit=100)
        for a in atts:
            c = a.get("comment", "")
            print(f"  witness {a.get('user')}: {c}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="ritual", description=ENTRY_BANNER)
    sub = ap.add_subparsers(dest="cmd")

    at = sub.add_parser("attest", help="Witness or comment on an event")
    at.add_argument("event")
    at.add_argument("--comment")
    at.add_argument("--quote")
    at.add_argument("--user")
    at.set_defaults(func=cmd_attest)

    ex = sub.add_parser("export", help="Export ritual ledger")
    ex.add_argument("--user", default="all")
    ex.set_defaults(func=cmd_export)

    tl = sub.add_parser("timeline", help="Show event timeline")
    tl.add_argument("--user")
    tl.set_defaults(func=cmd_timeline)

    args = ap.parse_args()
    print_banner()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()
    print_closing()


if __name__ == "__main__":
    main()
