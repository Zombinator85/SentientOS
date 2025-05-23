import argparse
import memory_manager as mm


def main():
    parser = argparse.ArgumentParser(description="Manage memory fragments")
    sub = parser.add_subparsers(dest="cmd")

    purge = sub.add_parser("purge", help="Delete old fragments")
    purge.add_argument("--age", type=int, help="Remove fragments older than N days")
    purge.add_argument("--max", type=int, help="Keep only the newest N fragments")

    sub.add_parser("summarize", help="Create/update daily summary files")

    args = parser.parse_args()
    if args.cmd == "purge":
        mm.purge_memory(max_age_days=args.age, max_files=args.max)
    elif args.cmd == "summarize":
        mm.summarize_memory()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
