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


def _play(path: str, user: str, share: str | None = None) -> dict:
    print(f"Playing {path}")
    feeling = input("Feeling> ").strip()
    reported = _parse_emotion(feeling)
    entry = ledger.log_music_listen(path, user=user, reported=reported)
    pl.log(user or "anon", "music_played", path)
    if share:
        share_entry = ledger.log_music_share(path, peer=share, user=user, emotion=reported)
        ledger.log_federation(share, message="music_share")
        return {"listen": entry, "share": share_entry}
    return entry


def _recap_emotion(limit: int = 20) -> dict:
    path = Path("logs/music_log.jsonl")
    totals: dict[str, float] = {}
    journey: list[dict[str, object]] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
        for ln in lines:
            try:
                e = json.loads(ln)
            except Exception:
                continue
            emo = {}
            for k in ("intended", "perceived", "reported", "received"):
                emo.update(e.get("emotion", {}).get(k) or {})
            for k, v in emo.items():
                totals[k] = totals.get(k, 0.0) + v
            journey.append({"time": e.get("timestamp"), "mood": list(emo.keys())})
    return {"totals": totals, "journey": journey}


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
    play.add_argument("--share", metavar="PEER", help="Share track with federation peer")

    recap = sub.add_parser("recap", help="Show recent music summary")
    recap.add_argument("--emotion", action="store_true", help="Summarize by emotion")
    recap.add_argument("--limit", type=int, default=20)

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
            entry = _play(args.file, args.user, share=args.share)
            print(json.dumps(entry, indent=2))
            print_closing_recap()
            recap_shown = True
        elif args.cmd == "recap" and args.emotion:
            data = _recap_emotion(args.limit)
            print(json.dumps(data, indent=2))
            print_closing_recap()
            recap_shown = True
        else:
            parser.print_help()
    finally:
        print_closing(show_recap=not recap_shown)


if __name__ == "__main__":
    main()
