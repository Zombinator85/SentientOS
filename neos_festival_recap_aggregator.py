from __future__ import annotations
from logging_config import get_log_path

from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
"""NeosVR Cross-World Festival Recap Aggregator."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = get_log_path("neos_recap_aggregate.jsonl", "NEOS_RECAP_AGGREGATE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_recap(source: str, note: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": source,
        "note": note,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_recaps(term: str = "") -> List[Dict[str, str]]:
    rec = read_json(LOG_PATH)
    if term:
        rec = [r for r in rec if term in json.dumps(r)]
    return rec


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Festival Recap Aggregator")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log recap")
    lg.add_argument("source")
    lg.add_argument("--note", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_recap(a.source, a.note), indent=2)))

    ls = sub.add_parser("list", help="List recaps")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_recaps(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
