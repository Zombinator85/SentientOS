#!/usr/bin/env python3
"""CLI for the operator-started bounded maintenance cadence runner."""
from __future__ import annotations
import argparse
from typing import Sequence
from sentientos import maintenance_loop_scheduler as scheduler

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="operator-started bounded maintenance cadence runner")
    parser.add_argument("--config", required=True); parser.add_argument("--evaluation-time")
    parser.add_argument("command", choices=("doctor", "run-once", "run-bounded", "inspect"))
    args = parser.parse_args(argv)
    try:
        cfg = scheduler.load_config(args.config)
        if args.command == "doctor": out = scheduler.doctor(cfg)
        elif args.command == "inspect": out = scheduler.inspect(cfg)
        elif args.command == "run-once":
            if not args.evaluation_time: parser.error("--evaluation-time is required for run-once")
            out = scheduler.run_once(cfg, evaluation_time=args.evaluation_time)
        else: out = scheduler.run_bounded(cfg)
        print(scheduler.canonical_bytes(out).decode()); return 0
    except (OSError, ValueError, KeyError) as exc:
        print(scheduler.canonical_bytes({"schema_version": "sentientos.maintenance_scheduler_error:v1", "status": "maintenance_scheduler_blocked", "reason": str(exc)}).decode()); return 2

if __name__ == "__main__": raise SystemExit(main())
