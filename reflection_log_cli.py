"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import argparse
import datetime
import os
from pathlib import Path
LOG_DIR = get_log_path("self_reflections", "REFLECTION_LOG_DIR")


def load_entries():
    files = sorted(LOG_DIR.glob("*.log"), reverse=True)
    for fp in files:
        day = fp.stem
        lines = fp.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            yield day, line


def export_day(day: str, out_file: Path, markdown: bool = False) -> bool:
    """Export all reflections for ``day`` to ``out_file``."""
    fp = LOG_DIR / f"{day}.log"
    if not fp.exists():
        return False
    lines = fp.read_text(encoding="utf-8").splitlines()
    if markdown:
        text = "\n".join(f"- {ln}" for ln in lines)
    else:
        text = "\n".join(lines)
    out_file.write_text(text, encoding="utf-8")
    return True


def search_entries(keyword: str, context: int = 20):
    """Yield (day, snippet) for entries containing ``keyword``."""
    key = keyword.lower()
    for day, line in load_entries():
        idx = line.lower().find(key)
        if idx == -1:
            continue
        start = max(0, idx - context)
        end = idx + len(keyword) + context
        yield day, line[start:end]


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Reflection log viewer")
    sub = parser.add_subparsers(dest="cmd")

    search = sub.add_parser("search")
    search.add_argument("keyword")
    search.add_argument("--context", type=int, default=20)
    search.add_argument("--limit", type=int, default=0)

    parser.add_argument("--date")
    parser.add_argument("--keyword")
    parser.add_argument("--last", type=int, default=5)
    parser.add_argument("--export")
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "search":
        results = []
        for day, snippet in search_entries(args.keyword, context=args.context):
            results.append(f"[{day}] {snippet}")
            if args.limit and len(results) >= args.limit:
                break
        print("\n".join(results))
        return
    if args.export:
        day = args.date or datetime.date.today().isoformat()
        ok = export_day(day, Path(args.export), markdown=args.markdown)
        if ok:
            print(f"Exported {day} to {args.export}")
        else:
            print("No entries to export")
        return

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
