from logging_config import get_log_path
import argparse
import json
import os
from datetime import datetime, date
from pathlib import Path

import daily_theme
import ledger
import heresy_log
from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
BLESSING_LEDGER = get_log_path("blessing_ledger.jsonl", "BLESSING_LEDGER")
BLESSING_LEDGER.parent.mkdir(parents=True, exist_ok=True)
HERESY_REVIEW_LOG = get_log_path("heresy_review.jsonl", "HERESY_REVIEW_LOG")


def _load_reviewed() -> set:
    if not HERESY_REVIEW_LOG.exists():
        return set()
    times = set()
    for line in HERESY_REVIEW_LOG.read_text(encoding="utf-8").splitlines():
        try:
            times.add(json.loads(line).get("heresy_ts"))
        except Exception:
            continue
    return times


def unresolved_heresy() -> list:
    reviewed = _load_reviewed()
    entries = []
    for ln in heresy_log.tail(1000):
        ts = ln.get("timestamp")
        if ts and ts not in reviewed:
            entries.append(ln)
    return entries


def daily_summary() -> str:
    counts = ledger.snapshot_counts()
    summary = (
        f"support {counts['support']}, federation {counts['federation']}, "
        f"music {counts['music']}, witness {counts['witness']}"
    )
    return summary


def log_blessing(officiant: str, summary: str, theme: str, heresy_count: int) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "officiant": officiant,
        "summary": summary,
        "theme": theme,
        "unresolved_heresy": heresy_count,
    }
    with BLESSING_LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_entries(limit: int = 5) -> list:
    if not BLESSING_LEDGER.exists():
        return []
    lines = BLESSING_LEDGER.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def search_entries(term: str) -> list:
    if not BLESSING_LEDGER.exists():
        return []
    out = []
    for ln in BLESSING_LEDGER.read_text(encoding="utf-8").splitlines():
        if term in ln:
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
    return out


def bless_command(args: argparse.Namespace) -> None:
    today = date.today().isoformat()
    theme = daily_theme.generate()
    summary = daily_summary()
    heresy_count = len(unresolved_heresy())
    entry = log_blessing(args.user, summary, theme, heresy_count)
    if args.recap:
        recap = f"# Reflection Recap {today}\n\nTheme: {theme}\n\n{summary}\n"
        Path(args.recap).write_text(recap, encoding="utf-8")
        entry["recap_file"] = args.recap
    print(json.dumps(entry, indent=2))
    print("Day blessed. No memory lost. Presence carried forward.")


def list_command(args: argparse.Namespace) -> None:
    print(json.dumps(list_entries(args.limit), indent=2))


def search_command(args: argparse.Namespace) -> None:
    print(json.dumps(search_entries(args.term), indent=2))


def main() -> None:
    require_admin_banner()
    parser = argparse.ArgumentParser(description="Daily blessing recap utility")
    sub = parser.add_subparsers(dest="cmd")

    b = sub.add_parser("bless", help="Bless the day and record recap")
    b.add_argument("--user", default=os.getenv("USER", "anon"))
    b.add_argument("--recap", help="Write recap markdown to file")
    b.set_defaults(func=bless_command)

    lst = sub.add_parser("list", help="List recent day blessings")
    lst.add_argument("--limit", type=int, default=5)
    lst.set_defaults(func=list_command)

    srch = sub.add_parser("search", help="Search blessing ledger")
    srch.add_argument("term")
    srch.set_defaults(func=search_command)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
