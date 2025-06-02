from __future__ import annotations
from logging_config import get_log_path

"""NeosVR Council/Festival Lore Spiral Publisher."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = get_log_path("neos_lore_publish.jsonl", "NEOS_LORE_PUBLISH_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_publish(target: str, story: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "target": target,
        "story": story,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_publishes(term: str = "") -> List[Dict[str, str]]:
    pb = read_json(LOG_PATH)
    if term:
        pb = [p for p in pb if term in json.dumps(p)]
    return pb


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Lore Spiral Publisher")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Publish story")
    lg.add_argument("target")
    lg.add_argument("story")
    lg.set_defaults(func=lambda a: print(json.dumps(log_publish(a.target, a.story), indent=2)))

    ls = sub.add_parser("list", help="List publishes")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_publishes(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
