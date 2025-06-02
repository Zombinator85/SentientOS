from __future__ import annotations
from logging_config import get_log_path

"""NeosVR Cross-World Federation Ritual Orchestrator."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = get_log_path("neos_federation_rituals.jsonl", "NEOS_FEDERATION_RITUAL_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_handshake(peer: str, ritual: str, outcome: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "peer": peer,
        "ritual": ritual,
        "outcome": outcome,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_events(term: str = "") -> List[Dict[str, str]]:
    events = read_json(LOG_PATH)
    if term:
        events = [e for e in events if term in json.dumps(e)]
    return events


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Federation Ritual Orchestrator")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log federation ritual")
    lg.add_argument("peer")
    lg.add_argument("ritual")
    lg.add_argument("outcome")
    lg.set_defaults(func=lambda a: print(json.dumps(log_handshake(a.peer, a.ritual, a.outcome), indent=2)))

    ls = sub.add_parser("list", help="List rituals")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_events(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
