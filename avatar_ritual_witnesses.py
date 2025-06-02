from __future__ import annotations
from logging_config import get_log_path

"""Avatars as Ritual Witnesses."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_witnesses.jsonl", "AVATAR_WITNESS_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_witness(event: str, avatar: str, note: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": event,
        "avatar": avatar,
        "note": note,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_witnesses(event: str | None = None) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
            if event is None or e.get("event") == event:
                out.append(e)
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Ritual Witnesses")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log a witness")
    lg.add_argument("event")
    lg.add_argument("avatar")
    lg.add_argument("--note", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_witness(a.event, a.avatar, a.note), indent=2)))

    ls = sub.add_parser("list", help="List witnesses")
    ls.add_argument("--event", default=None)
    ls.set_defaults(func=lambda a: print(json.dumps(list_witnesses(event=a.event), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
