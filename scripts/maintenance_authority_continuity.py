#!/usr/bin/env python3
"""CLI for bounded maintenance authority continuity evidence derivation."""
from __future__ import annotations
import argparse
from typing import Sequence
from sentientos import maintenance_authority_continuity as continuity

def main(argv: Sequence[str] | None = None) -> int:
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="command",required=True)
    for name in ("doctor","inspect","inspect-receipts"):
        p=sub.add_parser(name); p.add_argument("--policy",required=True)
    derive=sub.add_parser("derive-next"); derive.add_argument("--policy",required=True); derive.add_argument("--completion-evidence",required=True); derive.add_argument("--successor-evidence",required=True); derive.add_argument("--evaluation-time",required=True)
    a=parser.parse_args(argv)
    if a.command=="derive-next": result=continuity.derive_next(a.policy,a.completion_evidence,a.successor_evidence,a.evaluation_time)
    elif a.command=="inspect-receipts": result=continuity.inspect_receipts(a.policy)
    else: result=continuity.inspect(a.policy)
    print(continuity.canonical_bytes(result).decode())
    return 0 if result["status"] in {"continuity_ready","successor_generation_ready"} else 2

if __name__ == "__main__": raise SystemExit(main())
