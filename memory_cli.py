import argparse
from memory_manager import purge_memory, summarize_memory


def main():
    parser = argparse.ArgumentParser(description="Manage SentientOS memory")
    subparsers = parser.add_subparsers(dest="command")

    purge = subparsers.add_parser("purge", help="Delete old memory fragments")
    purge.add_argument("--age", type=int, help="Remove fragments older than AGE days", dest="age")
    purge.add_argument("--max", type=int, help="Keep only the newest MAX fragments", dest="max_files")

    subparsers.add_parser("summarize", help="Concatenate daily summaries")

    args = parser.parse_args()

    if args.command == "purge":
        purge_memory(max_age_days=args.age, max_files=args.max_files)
    elif args.command == "summarize":
        summarize_memory()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
