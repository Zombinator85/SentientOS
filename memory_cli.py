import argparse
from memory_manager import purge_memory, summarize_memory


def main():
    parser = argparse.ArgumentParser(description="Memory management utilities")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_purge = sub.add_parser("purge", help="Delete old memory fragments")
    p_purge.add_argument("--age", type=int, help="Remove fragments older than AGE days")
    p_purge.add_argument("--max", type=int, dest="max_files", help="Keep at most MAX fragments")

    sub.add_parser("summarize", help="Write daily summaries of memory")

    args = parser.parse_args()

    if args.cmd == "purge":
        purge_memory(max_age_days=args.age, max_files=args.max_files)
    elif args.cmd == "summarize":
        summarize_memory()


if __name__ == "__main__":
    main()
