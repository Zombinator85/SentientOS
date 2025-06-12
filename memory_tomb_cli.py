"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations
import argparse
import json
from pathlib import Path
import memory_manager as mm
TOMB_PATH = mm.TOMB_PATH


def load_entries():
    if not TOMB_PATH.exists():
        return []
    out = []
    for line in TOMB_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def list_entries(args: argparse.Namespace) -> None:
    entries = load_entries()
    for e in entries:
        ts = e.get("time")
        reason = e.get("reason", "")
        if args.date and args.date not in ts:
            continue
        if args.tag and args.tag not in reason:
            continue
        print(json.dumps(e, indent=2))


def wordcloud_command(args: argparse.Namespace) -> None:
    try:
        from wordcloud import WordCloud  # type: ignore  # wordcloud optional
    except Exception:
        print("wordcloud package required")
        return
    entries = load_entries()
    reasons = [e.get("reason", "") for e in entries]
    if not reasons:
        print("No entries")
        return
    wc = WordCloud(width=800, height=400, background_color="white")
    wc.generate(" ".join(reasons))
    wc.to_file(args.out)
    print(args.out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory tomb viewer")
    sub = parser.add_subparsers(dest="cmd")

    lst = sub.add_parser("list")
    lst.add_argument("--date")
    lst.add_argument("--tag")
    lst.set_defaults(func=list_entries)

    wc = sub.add_parser("wordcloud")
    wc.add_argument("out")
    wc.set_defaults(func=wordcloud_command)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
