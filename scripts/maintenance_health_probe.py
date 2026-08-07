#!/usr/bin/env python3
"""CLI for one bounded repository-native maintenance health probe."""
from __future__ import annotations
import argparse
from typing import Sequence
from sentientos import maintenance_health_probe as probe

def main(argv: Sequence[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="bounded maintenance health probe")
    parser.add_argument("--config",required=True)
    parser.add_argument("command",choices=("doctor","probe-once","inspect","print-run-command"))
    args=parser.parse_args(argv)
    try:
        cfg=probe.load_config(args.config)
        result={"doctor":probe.doctor,"probe-once":probe.probe_once,"inspect":probe.inspect,"print-run-command":probe.print_run_command}[args.command](cfg)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        result={"status":"health_probe_blocked","reason_codes":[str(exc)]}
    print(probe.canonical_json_bytes(result).decode())
    return 0 if result.get("status") in {"health_probe_ready","health_probe_healthy","health_probe_findings"} else 2

if __name__ == "__main__": raise SystemExit(main())
