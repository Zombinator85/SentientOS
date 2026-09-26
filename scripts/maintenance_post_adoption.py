"""Read/evaluate one explicitly named post-adoption protocol; no Git or rollback commands."""
from __future__ import annotations
import argparse, json
from dataclasses import asdict
from pathlib import Path
from typing import Any
from sentientos.maintenance_post_adoption_evaluation import MaintenancePostAdoptionEvaluationOwner


def main(argv: list[str]|None=None) -> int:
    parser=argparse.ArgumentParser(prog="maintenance-post-adoption")
    parser.add_argument("--state-root",required=True)
    sub=parser.add_subparsers(dest="command",required=True)
    for name in ("protocol-show","baseline-show","readiness","result-show","signal-show","verify"):
        item=sub.add_parser(name); item.add_argument("--protocol-id")
    args=parser.parse_args(argv); owner=MaintenancePostAdoptionEvaluationOwner(Path(args.state_root))
    value: Any
    if args.command=="verify": value=owner.verify()
    elif args.command=="protocol-show": value=asdict(owner.protocol(args.protocol_id))
    elif args.command=="baseline-show": value=asdict(owner.baseline(args.protocol_id))
    elif args.command=="readiness":
        value={"protocol_id":args.protocol_id,"status":"terminal" if any(x["protocol_id"]==args.protocol_id for x in owner._read("evaluations")) else "waiting_for_successor","authority":False}
    else:
        kind="evaluations" if args.command=="result-show" else "signals"
        rows=[x for x in owner._read(kind) if x.get("protocol_id")==args.protocol_id or x.get("spec_id")==args.protocol_id]
        value={"records":rows,"authority":False}
    print(json.dumps(value,sort_keys=True)); return 0


if __name__=="__main__": raise SystemExit(main())
