import argparse
import json
import os

import confessional_log as clog
import confessional_review as crev


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

    args = parser.parse_args(argv)
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
