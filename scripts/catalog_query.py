from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos import artifact_catalog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Query local artifact catalog")
    parser.add_argument("--latest", dest="latest_kind")
    parser.add_argument("--recent", dest="recent_kind")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--incident")
    parser.add_argument("--trace")
    parser.add_argument("--quarantine-latest", action="store_true")
    args = parser.parse_args(argv)
    root = Path.cwd().resolve()

    result: object
    if args.quarantine_latest:
        result = artifact_catalog.latest_quarantine_incident(root)
    elif args.incident and args.latest_kind:
        result = artifact_catalog.latest_for_incident(root, args.incident, kind=args.latest_kind)
    elif args.trace and args.latest_kind:
        result = artifact_catalog.latest_for_trace(root, args.trace, kind=args.latest_kind)
    elif args.recent_kind:
        result = artifact_catalog.recent(root, args.recent_kind, limit=args.limit)
    elif args.latest_kind:
        result = artifact_catalog.latest(root, args.latest_kind)
    else:
        parser.error("choose one query mode")
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
