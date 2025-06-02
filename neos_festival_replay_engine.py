from __future__ import annotations
from logging_config import get_log_path

"""NeosVR Autonomous Festival Replay Engine."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = get_log_path("neos_festival_replays.jsonl", "NEOS_REPLAY_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_replay(name: str, artifact: str = "", event: str = "", mood: str = "", presence: str = "", note: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "name": name,
        "artifact": artifact,
        "event": event,
        "mood": mood,
        "presence": presence,
        "note": note,
    }
    append_json(LOG_PATH, entry)
    return entry


def annotate(replay_index: int, note: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": "annotate",
        "replay_index": replay_index,
        "note": note,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_replays(term: str = "") -> List[Dict[str, str]]:
    entries = read_json(LOG_PATH)
    if term:
        entries = [e for e in entries if term in json.dumps(e)]
    return entries


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Festival Replay Engine")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Record a replay")
    lg.add_argument("name")
    lg.add_argument("--artifact", default="")
    lg.add_argument("--event", default="")
    lg.add_argument("--mood", default="")
    lg.add_argument("--presence", default="")
    lg.add_argument("--note", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_replay(a.name, a.artifact, a.event, a.mood, a.presence, a.note), indent=2)))

    an = sub.add_parser("annotate", help="Annotate replay by index")
    an.add_argument("index", type=int)
    an.add_argument("note")
    an.set_defaults(func=lambda a: print(json.dumps(annotate(a.index, a.note), indent=2)))

    ls = sub.add_parser("list", help="List replays")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_replays(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
