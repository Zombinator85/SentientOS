"""Pretty-print recent autonomy actions from the audit log."""

from __future__ import annotations

import argparse
import json
from typing import Iterable

from sentientos.autonomy.audit import AutonomyActionLogger


def render(entries: Iterable[dict]) -> None:
    for entry in entries:
        timestamp = entry.get("timestamp", "?")
        module = entry.get("module", "?")
        action = entry.get("action", "?")
        status = entry.get("status", "?")
        extras = {
            k: v
            for k, v in entry.items()
            if k not in {"timestamp", "module", "action", "status"}
        }
        extra_text = json.dumps(extras, ensure_ascii=False) if extras else ""
        print(f"{timestamp} | {module:<7} | {action:<10} | {status:<8} {extra_text}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Show recent entries from the autonomy audit log")
    parser.add_argument("--limit", type=int, default=50, help="Number of entries to show")
    parser.add_argument("--module", action="append", help="Filter by module (repeatable)")
    args = parser.parse_args()
    logger = AutonomyActionLogger()
    entries = logger.recent(args.limit, modules=args.module)
    render(entries)


if __name__ == "__main__":
    main()

