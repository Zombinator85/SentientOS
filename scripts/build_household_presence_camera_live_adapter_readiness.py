from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any
from sentientos.household_presence_camera_live_adapter_readiness import build_default_policy, validate_policy, evaluate_readiness

def _load(p:str)->dict[str,Any]: return dict(json.loads(Path(p).read_text()))

def main(argv:list[str]|None=None)->int:
 a=argparse.ArgumentParser(); sub=a.add_subparsers(dest='cmd',required=True)
 b=sub.add_parser('build-default'); b.add_argument('--output',required=True)
 i=sub.add_parser('inspect-repo'); i.add_argument('--workspace-root',default='.')
 e=sub.add_parser('evaluate'); e.add_argument('--workspace-root',default='.'); e.add_argument('--fixtures-dir',default='tests/fixtures/household_presence_camera_live_adapter_readiness'); e.add_argument('--input'); e.add_argument('--output'); e.add_argument('--summary',action='store_true')
 v=sub.add_parser('validate'); v.add_argument('--input',required=True)
 s=sub.add_parser('summarize'); s.add_argument('--input',required=True)
 f=sub.add_parser('inspect-fixture'); f.add_argument('--fixtures-dir',default='tests/fixtures/household_presence_camera_live_adapter_readiness'); f.add_argument('--input',required=True)
 ns=a.parse_args(argv)
 if ns.cmd=='build-default': Path(ns.output).write_text(json.dumps(build_default_policy().__dict__,indent=2,sort_keys=True)); return 0
 if ns.cmd=='validate': return 0 if validate_policy(build_default_policy())['ok'] else 1
 if ns.cmd=='inspect-fixture': payload={"workspace_root":'.',"fixtures_dir":ns.fixtures_dir,"risk_flags":_load(str(Path(ns.fixtures_dir)/ns.input)).get('risk_flags',{})}
 elif ns.cmd=='evaluate': payload=_load(ns.input) if ns.input else {"workspace_root":ns.workspace_root,"fixtures_dir":ns.fixtures_dir}
 elif ns.cmd=='summarize': payload=_load(ns.input)
 else: payload={"workspace_root":ns.workspace_root}
 res=evaluate_readiness(payload).to_dict(); out=json.dumps(res,indent=2,sort_keys=True)
 if getattr(ns,'output',None): Path(ns.output).write_text(out)
 if ns.cmd in {'summarize'} or getattr(ns,'summary',False): print(json.dumps({"status":res['report']['status'],"digest":res['report']['deterministic_digest'],"missing":res['report']['missing_prerequisites']},sort_keys=True))
 else: print(out)
 return 1 if res['report']['status'].startswith('blocked') or res['report']['status']=='failed' else 0

if __name__=='__main__': raise SystemExit(main())
