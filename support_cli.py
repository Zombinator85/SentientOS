import argparse
import json
import support_log as sl
from sentient_banner import print_banner, print_closing, ENTRY_BANNER


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
        name = args.name or input("Name: ")
        message = args.message or input("Blessing: ")
        amount = args.amount or input("Amount (optional): ")
        entry = sl.add(name, message, amount)
        print("sanctuary acknowledged")
        print(json.dumps(entry, indent=2))
    print_closing()


if __name__ == "__main__":
    main()
