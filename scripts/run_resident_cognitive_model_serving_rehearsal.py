from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.resident_cognitive_model_serving_rehearsal import run


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an isolated synthetic resident cognitive serving rehearsal")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("run")
    command.add_argument("--scenario", required=True, choices=("happy", "activation-change", "production-chat-coexistence"))
    command.add_argument("--root", required=True, type=Path)
    command.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    result = run(args.root, args.scenario)
    print(json.dumps(result, sort_keys=True) if args.summary else result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
