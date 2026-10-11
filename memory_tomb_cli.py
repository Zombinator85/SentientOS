"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
import argparse
import json
import memory_manager as mm
TOMB_PATH = mm.TOMB_PATH


def load_entries():
    try:
        return mm.list_tomb()
    except mm.MemorySidecarIncompleteError as exc:
        print(f"Tomb history incomplete: {exc}")
        return None


def list_entries(args: argparse.Namespace) -> None:
    entries = load_entries()
    if entries is None:
        return
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
        from wordcloud import WordCloud  # type: ignore[import-untyped]  # wordcloud optional
    except Exception:
        print("wordcloud package required")
        return
    entries = load_entries()
    if entries is None:
        return
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
