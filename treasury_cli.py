import argparse
import json
from pathlib import Path

import love_treasury as lt


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
    if args.treasury:
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


def main() -> None:
    ap = argparse.ArgumentParser(prog="treasury")
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
    l.add_argument("--status")
    l.set_defaults(func=cmd_list)

    e = sub.add_parser("export", help="Export enshrined log")
    e.add_argument("id")
    e.set_defaults(func=cmd_export)

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
