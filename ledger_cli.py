import argparse
import json
from pathlib import Path
import ledger


SUPPORT_LOG = Path('logs/support_log.jsonl')
FED_LOG = Path('logs/federation_log.jsonl')


def cmd_open(args: argparse.Namespace) -> None:
    """Print all ledger entries in order."""
    for path in [SUPPORT_LOG, FED_LOG]:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                print(line)


def cmd_summary(args: argparse.Namespace) -> None:
    """Print a summary of ledger counts and recent entries."""
    sup = ledger.summarize_log(SUPPORT_LOG)
    fed = ledger.summarize_log(FED_LOG)
    data = {
        'support_count': sup['count'],
        'federation_count': fed['count'],
        'support_recent': sup['recent'],
        'federation_recent': fed['recent'],
    }
    print(json.dumps(data, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(prog="ledger", description="Living Ledger tools")
    ap.add_argument("--support", action="store_true", help="Record a supporter blessing")
    ap.add_argument("--summary", action="store_true", help="Show ledger summary and exit")
    ap.add_argument("--name")
    ap.add_argument("--message")
    ap.add_argument("--amount", default="")
    sub = ap.add_subparsers(dest="cmd")
    op = sub.add_parser("open", help="View all ledger entries")
    op.set_defaults(func=cmd_open)
    sm = sub.add_parser("summary", help="Show ledger summary")
    sm.set_defaults(func=cmd_summary)
    args = ap.parse_args()

    if args.support:
        name = args.name or input("Name: ")
        message = args.message or input("Message: ")
        amount = args.amount or input("Amount (optional): ")
        entry = ledger.log_support(name, message, amount)
        print(json.dumps(entry, indent=2))
        if not args.cmd and not args.summary:
            return

    if args.summary and not args.cmd:
        cmd_summary(args)
        return

    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
