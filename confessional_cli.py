"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
import argparse
import json
import os
import confessional_log as clog
import confessional_review as crev
from admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
def cmd_log(args: argparse.Namespace) -> None:
    entry = clog.log_confession(
        args.subsystem,
        args.event,
        args.detail,
        tags=args.tags,
        reflection=args.reflection,
        severity=args.severity,
    )
    print(json.dumps(entry, indent=2))


def cmd_list(args: argparse.Namespace) -> None:
    entries = clog.tail(args.limit)
    print(json.dumps(entries, indent=2))


def cmd_search(args: argparse.Namespace) -> None:
    entries = clog.search(args.term)
    print(json.dumps(entries, indent=2))


def cmd_review(args: argparse.Namespace) -> None:
    reviewed = crev.reviewed_timestamps()
    for entry in clog.tail(1000):
        ts = entry.get("timestamp")
        if ts in reviewed:
            continue
        print(json.dumps(entry, indent=2))
        note = input("Reflection note (blank to skip)> ").strip()
        if not note:
            continue
        crev.log_review(ts or "", args.user, note, status=args.status)
        print("Confession reflected.")


def cmd_council(args: argparse.Namespace) -> None:
    """Interactive council review for critical confessions."""
    for entry in clog.tail(1000):
        if entry.get("severity") != "critical":
            continue
        ts = entry.get("timestamp") or ""
        if crev.council_status(ts) == "resolved":
            continue
        print(json.dumps(entry, indent=2))
        decision = input("Decision (approve/reject/skip)> ").strip().lower()
        if decision not in {"approve", "reject"}:
            continue
        note = input("Council note> ").strip()
        crev.log_council_vote(ts, args.user, decision, note)
        print("Vote recorded.")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Confessional log CLI")
    sub = parser.add_subparsers(dest="cmd")

    log_p = sub.add_parser("log")
    log_p.add_argument("subsystem")
    log_p.add_argument("event")
    log_p.add_argument("detail")
    log_p.add_argument("--tags", nargs="*")
    log_p.add_argument("--reflection", default="")
    log_p.add_argument("--severity", default="info")
    log_p.set_defaults(func=cmd_log)

    list_p = sub.add_parser("list")
    list_p.add_argument("--limit", type=int, default=10)
    list_p.set_defaults(func=cmd_list)

    search_p = sub.add_parser("search")
    search_p.add_argument("term")
    search_p.set_defaults(func=cmd_search)

    review_p = sub.add_parser("review")
    review_p.add_argument("--user", default=os.getenv("USER", "anon"))
    review_p.add_argument("--status", default="resolved")
    review_p.set_defaults(func=cmd_review)

    council_p = sub.add_parser("council")
    council_p.add_argument("--user", default=os.getenv("USER", "anon"))
    council_p.set_defaults(func=cmd_council)

    args = parser.parse_args(argv)
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
