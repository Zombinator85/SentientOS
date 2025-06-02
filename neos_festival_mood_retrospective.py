from __future__ import annotations

"""NeosVR Festival Mood Retrospective Compiler."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = Path(os.getenv("NEOS_MOOD_RETROSPECTIVE_LOG", "logs/neos_mood_retrospective.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_retrospective(festival: str, summary: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "festival": festival,
        "summary": summary,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_retrospectives() -> List[Dict[str, str]]:
    return read_json(LOG_PATH)


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Mood Retrospective Compiler")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log retrospective")
    lg.add_argument("festival")
    lg.add_argument("summary")
    lg.set_defaults(func=lambda a: print(json.dumps(log_retrospective(a.festival, a.summary), indent=2)))

    ls = sub.add_parser("list", help="List retrospectives")
    ls.set_defaults(func=lambda a: print(json.dumps(list_retrospectives(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
