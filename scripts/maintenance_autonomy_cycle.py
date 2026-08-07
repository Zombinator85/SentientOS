#!/usr/bin/env python3
"""CLI for one externally scheduled, bounded maintenance autonomy cycle."""
from __future__ import annotations
import argparse
from typing import Sequence
from sentientos import maintenance_autonomy_cycle as cycle

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="bounded external maintenance autonomy cycle")
    parser.add_argument("--config", required=True); parser.add_argument("--evaluation-time", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "cycle-once", "inspect", "inspect-receipts", "print-run-command"):
        commands.add_parser(name)
    args = parser.parse_args(argv)
    try:
        cfg = cycle.load_config(args.config)
        if args.command == "doctor": result = cycle.doctor(cfg, evaluation_time=args.evaluation_time)
        elif args.command == "cycle-once": result = cycle.cycle_once(cfg, evaluation_time=args.evaluation_time)
        elif args.command == "inspect": result = cycle.inspect(cfg, evaluation_time=args.evaluation_time)
        elif args.command == "inspect-receipts": result = cycle.inspect_receipts(cfg)
        else: result = cycle.print_run_command(args.config, evaluation_time=args.evaluation_time)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {"status": "autonomy_cycle_blocked", "reason_codes": [str(exc)]}
    print(cycle.canonical_json_bytes(result).decode())
    return 0 if result.get("status") in {"autonomy_cycle_ready", "autonomy_cycle_idle", "autonomy_cycle_completed", "autonomy_cycle_continuing", "inspection_ready", "receipts_ready", "run_command_ready"} else 2

if __name__ == "__main__": raise SystemExit(main())
