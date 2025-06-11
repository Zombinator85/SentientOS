"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
require_admin_banner()
require_lumos_approval()
from admin_utils import require_admin_banner, require_lumos_approval

from logging_config import get_log_path
import argparse
import json
import os
from pathlib import Path
LOG_DIR = get_log_path("self_reflections", "REFLECTION_LOG_DIR")
TAG_FILE = get_log_path("reflection_tags.json", "REFLECTION_TAG_FILE")
TAG_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_tags() -> dict:
    if TAG_FILE.exists():
        try:
            return json.loads(TAG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_tags(data: dict) -> None:
    TAG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def tag_reflection(day: str, tag: str) -> bool:
    fp = LOG_DIR / f"{day}.log"
    if not fp.exists():
        return False
    data = load_tags()
    lines = fp.read_text(encoding="utf-8").splitlines()
    data.setdefault(tag, []).extend(lines)
    save_tags(data)
    return True


def search_tag(tag: str) -> list:
    data = load_tags()
    return data.get(tag, [])


def main() -> None:
    ap = argparse.ArgumentParser(description="Reflection tagging utility")
    sub = ap.add_subparsers(dest="cmd")

    t = sub.add_parser("tag")
    t.add_argument("day")
    t.add_argument("tag")
    t.set_defaults(cmd="tag")

    s = sub.add_parser("search")
    s.add_argument("tag")
    s.set_defaults(cmd="search")

    args = ap.parse_args()
    if args.cmd == "tag":
        if tag_reflection(args.day, args.tag):
            print("Tagged")
        else:
            print("No such day")
    elif args.cmd == "search":
        print("\n".join(search_tag(args.tag)))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
