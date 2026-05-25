from typing import Any
from __future__ import annotations
import argparse, json
from pathlib import Path
from sentientos.household_presence_camera_policy_chain import build_default_policy, evaluate_policy_chain, validate_policy

def _load(p: str) -> dict[str, Any]:
    return dict(json.loads(Path(p).read_text()))

def main(argv: list[str] | None = None) -> int:
 a=argparse.ArgumentParser(); sub=a.add_subparsers(dest='cmd',required=True)
 b=sub.add_parser('build-default'); b.add_argument('--output',required=True)
 r=sub.add_parser('run-fixture'); r.add_argument('--name',required=True); r.add_argument('--fixtures-dir',default='tests/fixtures/household_presence_camera_policy_chain'); r.add_argument('--output')
 e=sub.add_parser('evaluate'); e.add_argument('--input'); e.add_argument('--event'); e.add_argument('--config'); e.add_argument('--output');
 v=sub.add_parser('validate'); v.add_argument('--input',required=True)
 s=sub.add_parser('summarize'); s.add_argument('--input',required=True); s.add_argument('--summary',action='store_true')
 ns=a.parse_args(argv)
 if ns.cmd=='build-default': Path(ns.output).write_text(json.dumps(build_default_policy().__dict__,indent=2,sort_keys=True)); return 0
 if ns.cmd=='validate': return 0 if validate_policy(build_default_policy())['ok'] else 1
 if ns.cmd=='run-fixture': payload=_load(str(Path(ns.fixtures_dir)/ns.name));res=evaluate_policy_chain(payload).to_dict()
 elif ns.cmd in {'evaluate','summarize'}:
  payload=_load(ns.input) if ns.input else {'event':_load(ns.event),'config':_load(ns.config),'policy_flags':{}}
  res=evaluate_policy_chain(payload).to_dict()
 out=json.dumps(res,indent=2,sort_keys=True)
 if getattr(ns,'output',None): Path(ns.output).write_text(out)
 if ns.cmd=='summarize': print(json.dumps({'route':res['decision']['route'],'blocked':res['decision']['blocked'],'digest':res['digest']},sort_keys=True))
 else: print(out)
 rt=res['decision']['route']
 return 1 if (res['decision']['blocked'] or rt=='operator_review_required') else 0

if __name__=='__main__': raise SystemExit(main())
