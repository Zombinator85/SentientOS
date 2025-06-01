from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()  # enforced

import argparse
import json
from pathlib import Path

import presence_ledger as pl
import ledger
from sentient_banner import (
    print_banner,
    print_closing,
    print_snapshot_banner,
    print_closing_recap,
    reset_ritual_state,
    ENTRY_BANNER,
)


def _parse_emotion(text: str) -> dict:
    emotions = {}
    if not text:
        return emotions
    for part in text.split(','):
        if '=' in part:
            k, v = part.split('=', 1)
            try:
                emotions[k.strip()] = float(v)
            except ValueError:
                continue
        else:
            emotions[part.strip()] = 1.0
    return emotions


def main() -> None:
    require_admin_banner()
    parser = argparse.ArgumentParser(description=ENTRY_BANNER)
    sub = parser.add_subparsers(dest="cmd")

    create = sub.add_parser("create", help="Log creation of a video")
    create.add_argument("file")
    create.add_argument("title")
    create.add_argument("--prompt", default="")
    create.add_argument("--emotion", default="")
    create.add_argument("--user", default="anon")

    play = sub.add_parser("play", help="Watch a video and log emotion")
    play.add_argument("file")
    play.add_argument("--user", default="anon")

    args = parser.parse_args()

    reset_ritual_state()
    print_banner()
    print_snapshot_banner()
    recap_shown = False
    try:
        if args.cmd == "create":
            emo = _parse_emotion(args.emotion)
            entry = ledger.log_video_create(
                args.prompt,
                args.title,
                args.file,
                emo,
                user=args.user,
            )
            pl.log(args.user, "video_created", args.title)
            print(json.dumps(entry, indent=2))
            print_closing_recap()
            recap_shown = True
        elif args.cmd == "play":
            feeling = input("Feeling> ").strip()
            perce = _parse_emotion(feeling)
            entry = ledger.log_video_watch(
                args.file,
                user=args.user,
                perceived=perce,
            )
            pl.log(args.user, "video_played", args.file)
            print(json.dumps(entry, indent=2))
            print_closing_recap()
            recap_shown = True
        else:
            parser.print_help()
    finally:
        print_closing(show_recap=not recap_shown)


if __name__ == "__main__":
    main()
