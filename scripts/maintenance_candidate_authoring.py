#!/usr/bin/env python3
"""CLI for explicit maintenance-candidate authoring and inert enqueue."""
from __future__ import annotations
import argparse
import json
from typing import Sequence
from sentientos import maintenance_candidate_authoring as authoring

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("write-candidate-template"); template.add_argument("--output", required=True)
    render = sub.add_parser("render-candidate"); render.add_argument("--manifest", required=True)
    for name in ("verify-candidate", "enqueue-candidate", "inspect-candidate", "print-pilot-plan"):
        item = sub.add_parser(name)
        for arg in ("manifest", "candidate", "receipt", "evaluation-time"): item.add_argument("--" + arg, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "write-candidate-template": out = authoring.write_candidate_template(args.output)
        elif args.command == "render-candidate": out = authoring.render_candidate(args.manifest)
        else:
            fn = getattr(authoring, args.command.replace("-", "_")); out = fn(args.manifest, args.candidate, args.receipt, args.evaluation_time)
        print(authoring.canonical_bytes(out).decode()); return 0 if out.get("status") not in {"candidate_blocked"} else 2
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(authoring.canonical_bytes({"schema_version":"sentientos.maintenance_candidate_authoring_error:v1","status":"candidate_blocked","reason_codes":[str(exc)]}).decode()); return 2
if __name__ == "__main__": raise SystemExit(main())
