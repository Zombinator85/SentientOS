import argparse
import json
from pathlib import Path
import memory_manager as mm


def show_timeline(last: int) -> None:
    """Print the timestamp and dominant emotion of recent entries."""
    path = mm.RAW_PATH
    files = sorted(path.glob("*.json"))[-last:]
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        emo = data.get("emotions", {})
        if emo:
            label = max(emo, key=emo.get)
            val = emo[label]
        else:
            label = "none"
            val = 0
        print(f"{data.get('timestamp','?')} {label}:{val:.2f}")


def main():
    parser = argparse.ArgumentParser(description="Manage memory fragments")
    sub = parser.add_subparsers(dest="cmd")

    purge = sub.add_parser("purge", help="Delete old fragments")
    purge.add_argument("--age", type=int, help="Remove fragments older than N days")
    purge.add_argument("--max", type=int, help="Keep only the newest N fragments")

    sub.add_parser("summarize", help="Create/update daily summary files")

    sub.add_parser("inspect", help="Print the user profile")
    plot = sub.add_parser("timeline", help="Show recent emotion timeline")
    plot.add_argument("--last", type=int, default=10, help="Show last N entries")
    forget = sub.add_parser("forget", help="Remove keys from user profile")
    forget.add_argument("keys", nargs="+", help="Profile keys to remove")

    args = parser.parse_args()
    if args.cmd == "purge":
        mm.purge_memory(max_age_days=args.age, max_files=args.max)
    elif args.cmd == "summarize":
        mm.summarize_memory()
    elif args.cmd == "inspect":
        import user_profile as up
        print(up.format_profile())
    elif args.cmd == "forget":
        import user_profile as up
        up.forget_keys(args.keys)
        print("Removed keys: " + ", ".join(args.keys))
    elif args.cmd == "timeline":
        show_timeline(args.last)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
