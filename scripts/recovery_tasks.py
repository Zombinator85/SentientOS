from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.recovery_tasks import list_tasks, mark_done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect recovery task queue")
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_parser = sub.add_parser("list", help="List recovery task records")
    list_parser.add_argument("--open-only", action="store_true")

    done_parser = sub.add_parser("done", help="Mark a task kind as done")
    done_parser.add_argument("kind")
    done_parser.add_argument("--note", default="")

    args = parser.parse_args(argv)
    root = Path.cwd()
    if args.cmd == "list":
        rows = list_tasks(root)
        if args.open_only:
            done_kinds = {str(row.get("kind")) for row in rows if str(row.get("status")) == "done"}
            rows = [row for row in rows if str(row.get("status", "open")) != "done" and str(row.get("kind")) not in done_kinds]
        print(json.dumps({"tasks": rows}, indent=2, sort_keys=True))
        return 0
    if args.cmd == "done":
        payload = mark_done(root, kind=args.kind, note=args.note)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
