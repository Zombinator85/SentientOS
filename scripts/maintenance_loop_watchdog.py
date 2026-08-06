#!/usr/bin/env python3
"""CLI for the bounded external maintenance watchdog."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Sequence
from sentientos import maintenance_loop_watchdog as watchdog

def _emit(value: object) -> None:
    print(watchdog.canonical_json_bytes(value).decode())

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="bounded maintenance-loop watchdog")
    parser.add_argument("--config", required=True)
    parser.add_argument("--evaluation-time")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "scan", "decide", "tick", "run-bounded", "recover", "pause", "resume", "inspect", "inspect-control", "inspect-base-cursor"):
        sub.add_parser(name)
    args = parser.parse_args(argv); cfg = watchdog.load_config(args.config)
    timed = {"scan", "decide", "tick", "run-bounded", "recover", "pause", "resume"}
    if args.command in timed and not args.evaluation_time:
        parser.error("--evaluation-time is required for this command")
    if args.command == "doctor": out = {"status": "watchdog_config_ready", "config_digest": cfg["config_digest"]}
    elif args.command == "scan": out = watchdog.scan(cfg, evaluation_time=args.evaluation_time)
    elif args.command == "decide":
        scanned = watchdog.scan(cfg, evaluation_time=args.evaluation_time); out = watchdog.decide(cfg, scanned)
    elif args.command in {"tick", "recover"}: out = watchdog.tick(cfg, evaluation_time=args.evaluation_time)
    elif args.command == "run-bounded": out = watchdog.run_bounded(cfg, evaluation_time=args.evaluation_time)
    elif args.command in {"pause", "resume"}: out = watchdog.control(cfg, args.command, evaluation_time=args.evaluation_time)
    elif args.command == "inspect-control": out = watchdog.inspect_control(cfg)
    else:
        name = "watchdog_ticks.jsonl" if args.command == "inspect" else "maintenance_base_cursor.jsonl"
        path = Path(cfg["state_root"]) / name
        out = {"status": "ready", "records": [json.loads(x) for x in path.read_text().splitlines() if x] if path.exists() else []}
    _emit(out); return 0

if __name__ == "__main__":
    raise SystemExit(main())
