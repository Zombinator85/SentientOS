from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

import presence_ledger as pl
import ledger
from jukebox_integration import JukeboxIntegration
from sentient_banner import (
    print_banner,
    print_closing,
    print_snapshot_banner,
    print_closing_recap,
    reset_ritual_state,
    ENTRY_BANNER,
)


def _parse_emotion(text: str) -> dict:
    """Parse emotion string like 'Joy=0.8,Sadness=0.2'"""
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


async def _generate(prompt: str, emotion: dict, user: str) -> dict:
    juke = JukeboxIntegration()
    path = await juke.generate_music(prompt, emotion)
    h = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    entry = ledger.log_music(prompt, emotion, path, h, user)
    pl.log(user or "anon", "music_generated", prompt)
    return entry


def _play(path: str, user: str) -> dict:
    print(f"Playing {path}")
    feeling = input("Feeling> ").strip()
    reported = _parse_emotion(feeling)
    entry = ledger.log_music_listen(path, user=user, reported=reported)
    pl.log(user or "anon", "music_played", path)
    return entry


def main() -> None:
    require_admin_banner()
    parser = argparse.ArgumentParser(description=ENTRY_BANNER)
    sub = parser.add_subparsers(dest="cmd")
    gen = sub.add_parser("generate", help="Generate music from a prompt")
    gen.add_argument("prompt")
    gen.add_argument("--emotion", default="", help="Comma separated emotion=val pairs")
    gen.add_argument("--user", default="anon")

    play = sub.add_parser("play", help="Play a music file and log emotion")
    play.add_argument("file")
    play.add_argument("--user", default="anon")

    args = parser.parse_args()

    reset_ritual_state()
    print_banner()
    print_snapshot_banner()
    recap_shown = False
    try:
        if args.cmd == "generate":
            emo = _parse_emotion(args.emotion)
            entry = asyncio.run(_generate(args.prompt, emo, args.user))
            print(json.dumps(entry, indent=2))
            print_closing_recap()
            recap_shown = True
        elif args.cmd == "play":
            entry = _play(args.file, args.user)
            print(json.dumps(entry, indent=2))
            print_closing_recap()
            recap_shown = True
        else:
            parser.print_help()
    finally:
        print_closing(show_recap=not recap_shown)


if __name__ == "__main__":
    main()
