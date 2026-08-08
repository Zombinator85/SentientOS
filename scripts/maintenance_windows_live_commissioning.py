#!/usr/bin/env python3
"""JSON-only CLI for one bounded Windows live commissioning invocation."""
from __future__ import annotations
import argparse
from typing import Sequence
from sentientos import maintenance_windows_live_commissioning as commissioning
from sentientos.maintenance_windows_live_bootstrap import canonical_bytes


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor"); doctor.add_argument("--manifest", required=True); doctor.add_argument("--state-root", required=True)
    run = sub.add_parser("commission-once"); run.add_argument("--manifest", required=True); run.add_argument("--state-root", required=True); run.add_argument("--create-custody-directories", action="store_true"); run.add_argument("--authorize-canary-defect", action="store_true")
    for name in ("inspect", "print-scheduler-install-command"):
        item = sub.add_parser(name); item.add_argument("--state-root", required=True)
    args = parser.parse_args(argv)
    if args.command == "doctor": result = commissioning.doctor(args.manifest, args.state_root)
    elif args.command == "commission-once": result = commissioning.commission_once(args.manifest, args.state_root, create_custody_directories=args.create_custody_directories, authorize_canary_defect=args.authorize_canary_defect)
    elif args.command == "inspect": result = commissioning.inspect(args.state_root)
    else: result = commissioning.print_scheduler_install_command(args.state_root)
    print(canonical_bytes(result).decode(), end="")
    return 2 if result.get("status") == commissioning.STATUS_BLOCKED else 0


if __name__ == "__main__": raise SystemExit(main())
