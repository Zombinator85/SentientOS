#!/usr/bin/env python3
"""CLI for one recovery-first bounded maintenance wake invocation."""
from __future__ import annotations
import argparse
from typing import Sequence
from sentientos import maintenance_wake_cycle as wake

def main(argv: Sequence[str]|None=None) -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--config",required=True); parser.add_argument("--evaluation-time"); parser.add_argument("command",choices=("doctor","wake-once","inspect","inspect-receipts","print-run-command")); args=parser.parse_args(argv)
    try:
        cfg=wake.load_config(args.config)
        if args.command=="doctor": result=wake.doctor(cfg,evaluation_time=args.evaluation_time)
        elif args.command=="wake-once": result=wake.wake_once(cfg,evaluation_time=args.evaluation_time)
        elif args.command=="inspect": result=wake.inspect(cfg,evaluation_time=args.evaluation_time)
        elif args.command=="inspect-receipts": result=wake.inspect_receipts(cfg)
        else: result=wake.print_run_command(args.config)
    except (OSError,ValueError,KeyError,TypeError) as exc: result={"status":"maintenance_wake_blocked","reason_codes":[str(exc)]}
    print(wake.canonical_json_bytes(result).decode())
    return 0 if result.get("status") in {"maintenance_wake_ready","maintenance_wake_idle","autonomy_cycle_idle","autonomy_cycle_completed","autonomy_cycle_continuing","autonomy_cycle_waiting","autonomy_cycle_paused","inspection_ready","receipts_ready","run_command_ready"} else 2
if __name__=="__main__": raise SystemExit(main())
