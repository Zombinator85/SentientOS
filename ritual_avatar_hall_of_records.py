from __future__ import annotations
from logging_config import get_log_path

"""Ritual Avatar Hall of Records.

Archives and searches important avatar ritual events.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_hall_of_records.jsonl", "AVATAR_HALL_RECORDS_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_record(record_type: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "type": record_type,
        "data": data,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_records(record_type: str | None = None) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
            if record_type is None or entry.get("type") == record_type:
                out.append(entry)
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Hall of Records")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log a record")
    lg.add_argument("type")
    lg.add_argument("data", nargs="*", help="key=value pairs")
    lg.set_defaults(
        func=lambda a: print(
            json.dumps(
                log_record(
                    a.type,
                    {k: v for k, v in (d.split("=", 1) for d in a.data)},
                ),
                indent=2,
            )
        )
    )

    ls = sub.add_parser("list", help="List records")
    ls.add_argument("--type", default=None)
    ls.set_defaults(
        func=lambda a: print(json.dumps(list_records(record_type=a.type), indent=2))
    )

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
