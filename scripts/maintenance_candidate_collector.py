#!/usr/bin/env python3
"""CLI for proposal-only governed maintenance candidate collection."""
from __future__ import annotations
import argparse
from pathlib import Path
from typing import Sequence
from sentientos import maintenance_candidate_collector as collector


def _emit(value: object) -> None:
    print(collector.canonical_json_bytes(value).decode("utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="governed maintenance candidate collector")
    parser.add_argument("--config", required=True)
    parser.add_argument("--evaluation-time")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "scan", "collect-once", "inspect", "inspect-receipts", "print-run-command"):
        sub.add_parser(name)
    args = parser.parse_args(argv)
    if args.command != "inspect-receipts" and not args.evaluation_time:
        parser.error("--evaluation-time is required")
    try:
        cfg = collector.load_config(args.config)
        if args.command == "doctor":
            result = collector.doctor(cfg, evaluation_time=args.evaluation_time)
        elif args.command == "scan":
            result = collector.scan(cfg, evaluation_time=args.evaluation_time)
        elif args.command == "collect-once":
            result = collector.collect_once(cfg, evaluation_time=args.evaluation_time)
        elif args.command == "inspect":
            result = collector.inspect(cfg, evaluation_time=args.evaluation_time)
        elif args.command == "inspect-receipts":
            result = collector.inspect_receipts(cfg)
        else:
            result = collector.print_run_command(Path(args.config), evaluation_time=args.evaluation_time)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {"status": "collector_blocked", "reason_codes": [str(exc)]}
    _emit(result)
    return 0 if str(result.get("status", "")).endswith("ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
