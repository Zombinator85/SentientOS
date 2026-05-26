from __future__ import annotations
import argparse, json
from pathlib import Path
from sentientos.household_presence_camera_host_inventory_bridge import build_default_policy, validate_policy, evaluate_inventory, load_inventory_fixture, dumps_result, inspect_repo_metadata

def _parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest='cmd',required=True)
    b=s.add_parser('build-default'); b.add_argument('--output'); b.add_argument('--summary',action='store_true')
    e=s.add_parser('evaluate'); e.add_argument('--input',required=True); e.add_argument('--output'); e.add_argument('--summary',action='store_true')
    v=s.add_parser('validate'); v.add_argument('--input',required=True)
    sm=s.add_parser('summarize'); sm.add_argument('--input',required=True)
    i=s.add_parser('inspect-fixture'); i.add_argument('--fixtures-dir',default='tests/fixtures/household_presence_camera_host_inventory_bridge'); i.add_argument('--input',required=True)
    r=s.add_parser('inspect-repo'); r.add_argument('--workspace-root',default='.')
    return p

def main()->int:
    a=_parser().parse_args()
    if a.cmd=='build-default':
        payload={"inventory_id":"default","devices":[]}
        out=dumps_result(evaluate_inventory(payload))
        if a.output: Path(a.output).write_text(out)
        print(out if not a.summary else json.dumps({"status":"ok"}))
        return 0
    if a.cmd=='evaluate':
        out=dumps_result(evaluate_inventory(load_inventory_fixture(a.input)))
        if a.output: Path(a.output).write_text(out)
        print(out if not a.summary else json.dumps({"status":"ok"}))
        return 0
    if a.cmd=='validate':
        ok=validate_policy(build_default_policy())["ok"]; print(json.dumps({"ok":ok})); return 0 if ok else 1
    if a.cmd=='summarize':
        d=json.loads(Path(a.input).read_text()); print(json.dumps({"status":d.get("report",{}).get("status"),"candidates":len(d.get("report",{}).get("candidates",[]))},sort_keys=True)); return 0
    if a.cmd=='inspect-fixture':
        d=load_inventory_fixture(str(Path(a.fixtures_dir)/a.input)); text=json.dumps(d).lower(); bad=any(k in text for k in ("base64","image","audio","video")); print(json.dumps({"fixture":a.input,"media_payload_forbidden":bad})); return 1 if bad else 0
    print(json.dumps(inspect_repo_metadata(a.workspace_root),sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
