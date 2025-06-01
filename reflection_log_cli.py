from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

import argparse
import os
from pathlib import Path


LOG_DIR = Path(os.getenv("REFLECTION_LOG_DIR", "logs/self_reflections"))


def load_entries():
    files = sorted(LOG_DIR.glob("*.log"), reverse=True)
    for fp in files:
        day = fp.stem
        lines = fp.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            yield day, line


def main(argv=None) -> None:
    require_admin_banner()
    parser = argparse.ArgumentParser(description="Reflection log viewer")
    parser.add_argument("--date")
    parser.add_argument("--keyword")
    parser.add_argument("--last", type=int, default=5)
    args = parser.parse_args(argv)

    count = 0
    for day, line in load_entries():
        if args.date and args.date not in day:
            continue
        if args.keyword and args.keyword.lower() not in line.lower():
            continue
        print(f"[{day}] {line}")
        count += 1
        if count >= args.last:
            break


if __name__ == "__main__":
    main()

