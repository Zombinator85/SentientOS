"""One-shot operator CLI for the governed avatar authoring workcell."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from sentientos.avatar_authoring import blender_readiness, lineage, validate_plan

def main() -> int:
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="command",required=True)
    plan=sub.add_parser("plan-validate"); plan.add_argument("plan")
    ready=sub.add_parser("readiness"); ready.add_argument("--blender",required=True); ready.add_argument("--driver",default=str(Path(__file__).with_name("avatar_blender_driver.py"))); ready.add_argument("--workspace-root",required=True); ready.add_argument("--executable-sha256")
    lin=sub.add_parser("lineage"); lin.add_argument("path")
    args=parser.parse_args()
    if args.command=="plan-validate": result=validate_plan(json.loads(Path(args.plan).read_text()))
    elif args.command=="readiness": result=blender_readiness(Path(args.blender),Path(args.driver),Path(args.workspace_root),expected_sha256=args.executable_sha256)
    else: result={"schema":"sentientos.avatar_body_lineage_query:v1","events":lineage(Path(args.path)),"authority":{}}
    print(json.dumps(result,sort_keys=True)); return 0 if not str(result.get("status","")).endswith("unavailable") else 2
if __name__=="__main__": raise SystemExit(main())
