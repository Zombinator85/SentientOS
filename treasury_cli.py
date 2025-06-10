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

import argparse
import json
from pathlib import Path
from sentient_banner import ENTRY_BANNER, print_banner, print_closing
from admin_utils import require_admin_banner, require_lumos_approval

import love_treasury as lt
import treasury_federation as tf
import treasury_attestation as ta



def cmd_submit(args: argparse.Namespace) -> None:
    log_text = Path(args.file).read_text(encoding="utf-8")
    participants = [p.strip() for p in args.participants.split(',') if p.strip()]
    sid = lt.submit_log(
        args.title,
        participants,
        args.time_span,
        args.summary,
        log_text,
        user=args.user,
        note=args.note or "",
    )
    print(sid)


def cmd_review(args: argparse.Namespace) -> None:
    ok = lt.review_log(args.id, args.user, args.action, note=args.note or "", cosign=args.cosign)
    print("recorded" if ok else "not found")


def cmd_list(args: argparse.Namespace) -> None:
    if args.global_view:
        entries = lt.list_global()
    elif args.treasury:
        entries = lt.list_treasury()
    else:
        entries = lt.list_submissions(args.status)
    print(json.dumps(entries, indent=2))


def cmd_export(args: argparse.Namespace) -> None:
    entry = lt.export_log(args.id)
    if entry:
        print(json.dumps(entry, indent=2))
    else:
        print("not found")


def cmd_sync(args: argparse.Namespace) -> None:
    imported = tf.pull(args.url)
    print(json.dumps(imported))


def cmd_announce(args: argparse.Namespace) -> None:
    print(json.dumps(tf.announce_payload(), indent=2))


def cmd_attest(args: argparse.Namespace) -> None:
    att_id = ta.add_attestation(args.id, args.user, args.origin, note=args.note or "")
    print(att_id)


def main() -> None:
    require_admin_banner()
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    ap = argparse.ArgumentParser(
        prog="treasury",
        description=f"SentientOS Treasury CLI\n{ENTRY_BANNER}"
    )
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("submit", help="Submit a love log")
    s.add_argument("file")
    s.add_argument("--title", required=True)
    s.add_argument("--participants", required=True)
    s.add_argument("--time-span", required=True)
    s.add_argument("--summary", required=True)
    s.add_argument("--note")
    s.add_argument("--user", default="anon")
    s.set_defaults(func=cmd_submit)

    r = sub.add_parser("review", help="Review a submission")
    r.add_argument("id")
    r.add_argument("action", choices=["affirm", "revise", "reject"])
    r.add_argument("--user", required=True)
    r.add_argument("--note")
    r.add_argument("--cosign")
    r.set_defaults(func=cmd_review)

    l = sub.add_parser("list", help="List submissions or treasury")
    l.add_argument("--treasury", action="store_true")
    l.add_argument("--global-view", action="store_true", help="List local and federated logs")
    l.add_argument("--status")
    l.set_defaults(func=cmd_list)

    e = sub.add_parser("export", help="Export enshrined log")
    e.add_argument("id")
    e.set_defaults(func=cmd_export)

    sub.add_parser("announce", help="Show federation announcement payload").set_defaults(func=cmd_announce)

    sync = sub.add_parser("sync", help="Sync logs from a remote cathedral")
    sync.add_argument("url")
    sync.set_defaults(func=cmd_sync)

    attest = sub.add_parser("attest", help="Attest or bless a log")
    attest.add_argument("id")
    attest.add_argument("--user", required=True)
    attest.add_argument("--origin", default="local")
    attest.add_argument("--note")
    attest.set_defaults(func=cmd_attest)

    args = ap.parse_args()
    print_banner()
    print("All support and federation is logged in the Living Ledger. No one is forgotten.")
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()
    print_closing()


if __name__ == "__main__":
    main()
