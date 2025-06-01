import argparse
import json
import support_log as sl
from sentient_banner import print_banner, ENTRY_BANNER


def main() -> None:
    p = argparse.ArgumentParser(prog="support", description=ENTRY_BANNER)
    p.add_argument("--support", action="store_true", help="Show contact and CashApp")
    p.add_argument("--bless", action="store_true", help="Record a supporter blessing")
    p.add_argument("--name")
    p.add_argument("--message")
    p.add_argument("--amount", default="")
    args = p.parse_args()

    print_banner()
    if args.support:
        print(ENTRY_BANNER)
    if args.bless:
        if not args.name or not args.message:
            p.error("--name and --message required with --bless")
        entry = sl.add(args.name, args.message, args.amount)
        print("sanctuary acknowledged")
        print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
