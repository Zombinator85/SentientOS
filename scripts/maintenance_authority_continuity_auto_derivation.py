"""CLI for the bounded maintenance continuity auto-derivation controller."""
from __future__ import annotations

import argparse
import json
from typing import Sequence

from sentientos import maintenance_authority_continuity_auto_derivation as auto

def main(argv: Sequence[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--config",required=True)
    parser.add_argument("command",choices=("doctor","inspect","inspect-receipts","derive-once"));ns=parser.parse_args(argv)
    try:
        cfg=auto.load_config(ns.config)
        result=auto.derive_once(cfg) if ns.command=="derive-once" else auto.inspect_receipts(cfg) if ns.command=="inspect-receipts" else auto.inspect(cfg)
        print(json.dumps(result,sort_keys=True,separators=(",",":")))
        return 0 if result.get("status") not in {"blocked","degraded"} else 2
    except Exception as exc:
        print(json.dumps({"schema_version":auto.RESULT_SCHEMA,"status":"blocked","reason":str(exc)},sort_keys=True,separators=(",",":")))
        return 2

if __name__ == "__main__": raise SystemExit(main())
