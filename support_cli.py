import argparse
import json
import support_log as sl


def main() -> None:
    p = argparse.ArgumentParser(prog="support", description="Record a support blessing")
    p.add_argument("--name", required=True)
    p.add_argument("--message", required=True)
    p.add_argument("--amount", default="")
    args = p.parse_args()
    entry = sl.add(args.name, args.message, args.amount)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
