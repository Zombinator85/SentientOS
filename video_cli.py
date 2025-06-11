"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
require_admin_banner()
require_lumos_approval()
from admin_utils import require_admin_banner, require_lumos_approval
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
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""  # plint: disable=banner-order
#  _____  _             _
# |  __ \| |           (_)
# | |__) | |_   _  __ _ _ _ __   __ _
# |  ___/| | | | |/ _` | | '_ \ / _` |
# | |    | | |_| | (_| | | | | | (_| |
# |_|    |_\__,_|\__, |_|_| |_|\__, |
#                  __/ |         __/ |
#                 |___/         |___/
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.



require_admin_banner()  # enforced




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
    play.add_argument("--share", metavar="PEER", help="Share clip with federation peer")

    share = sub.add_parser("share", help="Share a video clip with a peer")
    share.add_argument("file")
    share.add_argument("--peer", required=True)
    share.add_argument("--emotion", default="")
    share.add_argument("--user", default="anon")

    recap = sub.add_parser("recap", help="Show recent video summary")
    recap.add_argument("--limit", type=int, default=20)

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
                peer=args.share,
            )
            pl.log(args.user, "video_played", args.file)
            if args.share:
                share_entry = ledger.log_video_share(
                    args.file,
                    peer=args.share,
                    user=args.user,
                    emotion=perce,
                )
                ledger.log_federation(args.share, message="video_share")
                entry = {"watch": entry, "share": share_entry}
            print(json.dumps(entry, indent=2))
            print_closing_recap()
            recap_shown = True
        elif args.cmd == "share":
            emo = _parse_emotion(args.emotion)
            entry = ledger.log_video_share(
                args.file,
                peer=args.peer,
                user=args.user,
                emotion=emo,
            )
            ledger.log_federation(args.peer, message="video_share")
            pl.log(args.user, "video_shared", args.file)
            print(json.dumps(entry, indent=2))
            print_closing_recap()
            recap_shown = True
        elif args.cmd == "recap":
            data = ledger.video_recap(args.limit)
            print(json.dumps(data, indent=2))
            print_closing_recap()
            recap_shown = True
        else:
            parser.print_help()
    finally:
        print_closing(show_recap=not recap_shown)


if __name__ == "__main__":
    main()
