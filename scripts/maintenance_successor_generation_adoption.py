"""Operator CLI for bounded maintenance successor-generation adoption."""
from __future__ import annotations

import argparse
import json

from sentientos.maintenance_successor_generation_adoption import (
    MaintenanceSuccessorGenerationOwner, inspect, load_config,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("doctor", "inspect", "inspect-handoffs", "handoff-once"))
    parser.add_argument("config")
    args = parser.parse_args(); cfg = load_config(args.config)
    if args.command in {"doctor", "inspect"}:
        result = inspect(cfg)
    elif args.command == "inspect-handoffs":
        result = inspect(cfg)
    else:
        # Effectful use requires the daemon's canonical closure builder.  The CLI
        # intentionally cannot synthesize authority or accept caller-selected files.
        owner = MaintenanceSuccessorGenerationOwner(cfg)
        try: result = owner.handoff_once()
        except ValueError as exc: result = {"status": "blocked", "reason": str(exc), "effect_count": 0}
    print(json.dumps(result, sort_keys=True)); return 0 if result.get("status") != "blocked" else 2


if __name__ == "__main__": raise SystemExit(main())
