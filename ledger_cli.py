import argparse
import json
from pathlib import Path
import ledger


SUPPORT_LOG = Path('logs/support_log.jsonl')
FED_LOG = Path('logs/federation_log.jsonl')


def cmd_open(args: argparse.Namespace) -> None:
    for path in [SUPPORT_LOG, FED_LOG]:
        if path.exists():
            for line in path.read_text(encoding='utf-8').splitlines():
                print(line)


def cmd_summary(args: argparse.Namespace) -> None:
    sup = ledger.summary(SUPPORT_LOG)
    fed = ledger.summary(FED_LOG)
    data = {
        'support_count': sup['count'],
        'federation_count': fed['count'],
        'support_recent': sup['recent'],
        'federation_recent': fed['recent'],
    }
    print(json.dumps(data, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(prog='ledger', description='Living Ledger tools')
    sub = ap.add_subparsers(dest='cmd')
    op = sub.add_parser('open', help='Print all ledger entries')
    op.set_defaults(func=cmd_open)
    sm = sub.add_parser('summary', help='Show ledger summary')
    sm.set_defaults(func=cmd_summary)
    args = ap.parse_args()
    if hasattr(args, 'func'):
        args.func(args)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
