from logging_config import get_log_path
from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Dict

import presence_ledger as pl
import ledger
import mood_wall
from jukebox_integration import JukeboxIntegration
from sentient_banner import (
    print_banner,
    print_closing,
    print_snapshot_banner,
    print_closing_recap,
    reset_ritual_state,
    ENTRY_BANNER,
)


def _parse_emotion(text: str) -> Dict[str, float]:
    """Parse emotion string like 'Joy=0.8,Sadness=0.2'"""
    emotions: Dict[str, float] = {}
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


async def _generate(prompt: str, emotion: Dict[str, float], user: str) -> Dict[str, Any]:
    juke = JukeboxIntegration()
    path = await juke.generate_music(prompt, emotion)
    h = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    entry = ledger.log_music(prompt, emotion, path, h, user)
    pl.log(user or "anon", "music_generated", prompt)
    return entry


def _play(path: str, user: str, share: str | None = None) -> Dict[str, Any]:
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


def _recap_emotion(limit: int = 20) -> Dict[str, Any]:
    path = get_log_path("music_log.jsonl")
    totals: dict[str, float] = {}
    journey: list[dict[str, object]] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
        for ln in lines:
            try:
                e = json.loads(ln)
            except Exception:
                continue
            emo: Dict[str, float] = {}
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

    plst = sub.add_parser("playlist", help="Playlist from mood")
    plst.add_argument("mood")
    plst.add_argument("--limit", type=int, default=10)
    plst.add_argument("--user", default="anon")

    wall = sub.add_parser("wall", help="Show public Mood Wall")
    wall.add_argument("--limit", type=int, default=10)
    wall.add_argument("--bless", metavar="MOOD", help="Bless a mood on the wall")
    wall.add_argument("--message", default="", help="Blessing message")
    wall.add_argument("--user", default="anon")
    wall.add_argument("--sync", action="store_true", help="Sync mood wall from peers")
    wall.add_argument("--global", dest="global_bless", action="store_true", help="Propagate blessing to peers")

    refl = sub.add_parser("reflect", help="Log personal music reflection")
    refl.add_argument("note")
    refl.add_argument("--emotion", default="")
    refl.add_argument("--user", default="anon")

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
        elif args.cmd == "playlist":
            entries = ledger.playlist_by_mood(args.mood, args.limit)
            wall = mood_wall.load_wall(100)
            trending = ""
            tm = mood_wall.top_moods(wall)
            if tm:
                trending = max(tm.items(), key=lambda x: x[1])[0]
            reason = "requested"
            if trending:
                reason = f"trending mood {trending}"
                bless = mood_wall.latest_blessing_for(trending)
                if bless:
                    sender = bless.get("sender") or bless.get("user", "")
                    reason += f", blessed by {sender}"
            log = ledger.playlist_log(entries, args.mood, args.user, "local", reason=reason)
            print(json.dumps(log, indent=2))
            print_closing_recap()
            recap_shown = True
        elif args.cmd == "wall":
            if args.sync:
                peers = mood_wall.peers_from_federation()
                synced = 0
                for p in peers:
                    try:
                        synced += mood_wall.sync_wall_http(p)
                    except Exception:
                        continue
                print(json.dumps({"synced": synced}))
            if args.bless:
                if args.global_bless:
                    peers = mood_wall.peers_from_federation()
                    status = {}
                    for p in peers:
                        try:
                            ledger.log_mood_blessing(args.user, p, {args.bless: 1.0}, args.message or f"{args.user} blesses {args.bless}")
                            status[p] = "ok"
                        except Exception as e:  # pragma: no cover - sanity
                            status[p] = str(e)
                    print(json.dumps({"global_bless": status}, indent=2))
                else:
                    entry = mood_wall.bless_mood(args.bless, args.user, args.message)
                    print(json.dumps(entry, indent=2))
            wall = mood_wall.load_wall(args.limit)
            data = {"wall": wall, "top_moods": mood_wall.top_moods(wall)}
            print(json.dumps(data, indent=2))
            print_closing_recap()
            recap_shown = True
        elif args.cmd == "reflect":
            emo = _parse_emotion(args.emotion)
            entry = ledger.log_music_event("reflection", args.note, reported=emo, file_path="", user=args.user)
            first = ledger.music_recap(100)
            if first["emotion_totals"] and sum(first["emotion_totals"].values()) <= sum(emo.values()):
                ledger.log_mood_blessing(args.user, "self", emo, "First reflection")
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
