#!/usr/bin/env python3
"""Small JSON-only CLI for Windows host readiness and canary inspection."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any, Sequence
from sentientos import maintenance_windows_host_readiness as readiness

def main(argv: Sequence[str] | None = None) -> int:
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="command",required=True)
    inspect=sub.add_parser("inspect-host"); inspect.add_argument("--repository-root",default="."); inspect.add_argument("--custody-root",action="append",default=[])
    render=sub.add_parser("render-host-manifest"); render.add_argument("--input"); render.add_argument("--output");
    for field in sorted(readiness.FIELDS-{"schema_version"}): render.add_argument("--"+field.replace("_","-"))
    for name in ("verify-host-manifest","doctor-live","print-manual-canary-command","inspect-canary"):
        item=sub.add_parser(name); item.add_argument("--manifest",required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=="inspect-host": result=readiness.inspect_host(args.repository_root,args.custody_root)
        elif args.command=="render-host-manifest":
            values: dict[str,Any]={}
            if args.input: values=json.loads(Path(args.input).read_text(encoding="utf-8"))
            for field in readiness.FIELDS-{"schema_version"}:
                supplied=getattr(args,field)
                if supplied is not None: values[field]=supplied
            manifest=readiness.render_host_manifest(values); result={"status":"windows_host_manifest_rendered","manifest":manifest,"scheduler_mutation_performed":False}
            if args.output: Path(args.output).write_bytes(readiness.canonical_json_bytes(manifest)); result["output_path"]=args.output
        else:
            cfg=readiness.load_manifest(args.manifest)
            result=getattr(readiness,args.command.replace("-","_"))(cfg)
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
        result={"status":"windows_host_blocked","reason_codes":[str(exc)],"scheduler_mutation_performed":False}
    print(readiness.canonical_json_bytes(result).decode(),end="")
    return 0 if result.get("status") in {"windows_host_inspected","windows_host_manifest_rendered","windows_host_manifest_verified","windows_host_ready","manual_canary_command_ready","canary_not_started","canary_defect_present","canary_maintenance_active","canary_repaired_unpublished","canary_completed"} else 2
if __name__=="__main__": raise SystemExit(main())
