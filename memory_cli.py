import argparse
import memory_manager as mm


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage SentientOS memory")
    sub = parser.add_subparsers(dest="command")

    purge = sub.add_parser("purge", help="Delete old memory fragments")
    purge.add_argument("--age", type=int, dest="age", help="Remove fragments older than AGE days")
    purge.add_argument("--max", type=int, dest="max_files", help="Keep only the newest MAX fragments")

    sub.add_parser("summarize", help="Concatenate daily summaries")

    args = parser.parse_args()

    if args.command == "purge":
        mm.purge_memory(max_age_days=args.age, max_files=args.max_files)
    elif args.command == "summarize":
        mm.summarize_memory()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
