from __future__ import annotations
from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
"""Game world integration for Minecraft and Valheim.

This module logs in-game ritual events and acts as a bridge between
SentientOS and external worlds such as Minecraft or Valheim.
Each event is appended to ``logs/game_bridge_events.jsonl`` or the path
specified by the ``GAME_BRIDGE_LOG`` environment variable.
"""

from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("game_bridge_events.jsonl", "GAME_BRIDGE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _log(event: str, **data: str) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "event": event}
    entry.update(data)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def avatar_ritual_bridge(game: str, avatar: str, ritual: str, location: str) -> Dict[str, str]:
    """Record an avatar ritual being bridged to a game."""
    return _log("avatar_ritual_bridge", game=game, avatar=avatar, ritual=ritual, location=location)


def build_sanctuary(game: str, name: str, location: str) -> Dict[str, str]:
    """Log an auto-generated sanctuary."""
    return _log("build_sanctuary", game=game, name=name, location=location)


def memory_relic_drop(game: str, avatar: str, relic: str, location: str) -> Dict[str, str]:
    """Log a relic drop tied to an avatar."""
    return _log("memory_relic_drop", game=game, avatar=avatar, relic=relic, location=location)


def orchestrate_festival(game: str, festival: str, participants: List[str]) -> Dict[str, str]:
    """Log a festival event with participants."""
    return _log(
        "festival", game=game, festival=festival, participants=",".join(participants)
    )


def player_blessing(game: str, player: str, action: str) -> Dict[str, str]:
    """Log that a player earned a blessing."""
    return _log("player_blessing", game=game, player=player, action=action)


def teaching_session(game: str, avatar: str, topic: str, players: List[str]) -> Dict[str, str]:
    """Record an avatar-led teaching session."""
    return _log(
        "teaching_session", game=game, avatar=avatar, topic=topic, players=",".join(players)
    )


def lore_beacon(game: str, title: str, location: str) -> Dict[str, str]:
    """Log a lore beacon or exhibit."""
    return _log("lore_beacon", game=game, title=title, location=location)


def emotion_overlay(game: str, avatar: str, emotion: str, location: str) -> Dict[str, str]:
    """Log a real-time emotion overlay."""
    return _log(
        "emotion_overlay", game=game, avatar=avatar, emotion=emotion, location=location
    )


def heirloom_vault(game: str, action: str, item: str, location: str) -> Dict[str, str]:
    """Log storing or retrieving an heirloom."""
    return _log("heirloom_vault", game=game, action=action, item=item, location=location)


def presence_pulse(game: str, state: str) -> Dict[str, str]:
    """Log a cross-world presence pulse."""
    return _log("presence_pulse", game=game, state=state)


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Game world integration")
    sub = ap.add_subparsers(dest="cmd")

    ar = sub.add_parser("avatar-event", help="Bridge avatar ritual event")
    ar.add_argument("game")
    ar.add_argument("avatar")
    ar.add_argument("ritual")
    ar.add_argument("location")
    ar.set_defaults(
        func=lambda a: avatar_ritual_bridge(a.game, a.avatar, a.ritual, a.location)
    )

    bs = sub.add_parser("build-sanctuary", help="Log sanctuary build")
    bs.add_argument("game")
    bs.add_argument("name")
    bs.add_argument("location")
    bs.set_defaults(func=lambda a: build_sanctuary(a.game, a.name, a.location))

    mr = sub.add_parser("memory-relic", help="Log memory relic drop")
    mr.add_argument("game")
    mr.add_argument("avatar")
    mr.add_argument("relic")
    mr.add_argument("location")
    mr.set_defaults(
        func=lambda a: memory_relic_drop(a.game, a.avatar, a.relic, a.location)
    )

    fe = sub.add_parser("festival", help="Log festival event")
    fe.add_argument("game")
    fe.add_argument("festival")
    fe.add_argument("participants", help="comma-separated list")
    fe.set_defaults(
        func=lambda a: orchestrate_festival(a.game, a.festival, a.participants.split(","))
    )

    pb = sub.add_parser("player-blessing", help="Log player blessing")
    pb.add_argument("game")
    pb.add_argument("player")
    pb.add_argument("action")
    pb.set_defaults(func=lambda a: player_blessing(a.game, a.player, a.action))

    ts = sub.add_parser("teaching", help="Log teaching session")
    ts.add_argument("game")
    ts.add_argument("avatar")
    ts.add_argument("topic")
    ts.add_argument("players", help="comma-separated list")
    ts.set_defaults(
        func=lambda a: teaching_session(a.game, a.avatar, a.topic, a.players.split(","))
    )

    lb = sub.add_parser("lore-beacon", help="Log lore beacon placement")
    lb.add_argument("game")
    lb.add_argument("title")
    lb.add_argument("location")
    lb.set_defaults(func=lambda a: lore_beacon(a.game, a.title, a.location))

    eo = sub.add_parser("emotion-overlay", help="Log emotion overlay")
    eo.add_argument("game")
    eo.add_argument("avatar")
    eo.add_argument("emotion")
    eo.add_argument("location")
    eo.set_defaults(
        func=lambda a: emotion_overlay(a.game, a.avatar, a.emotion, a.location)
    )

    hv = sub.add_parser("heirloom-vault", help="Log heirloom vault action")
    hv.add_argument("game")
    hv.add_argument("action")
    hv.add_argument("item")
    hv.add_argument("location")
    hv.set_defaults(
        func=lambda a: heirloom_vault(a.game, a.action, a.item, a.location)
    )

    pp = sub.add_parser("presence-pulse", help="Log presence pulse state")
    pp.add_argument("game")
    pp.add_argument("state")
    pp.set_defaults(func=lambda a: presence_pulse(a.game, a.state))

    args = ap.parse_args()
    if hasattr(args, "func"):
        entry = args.func(args)
        print(json.dumps(entry, indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
