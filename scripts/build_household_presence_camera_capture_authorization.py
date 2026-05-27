from __future__ import annotations
import argparse, json
from pathlib import Path
from sentientos.household_presence_camera_capture_authorization import build_default_policy, evaluate_capture_authorization, validate_policy

def _read(p:str)->dict:
    return json.loads(Path(p).read_text())

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('command',choices=['build-default','evaluate','validate','summarize','inspect-fixture'])
    ap.add_argument('--input');ap.add_argument('--fixtures-dir',default='tests/fixtures/household_presence_camera_capture_authorization');ap.add_argument('--output');ap.add_argument('--summary',action='store_true');ap.add_argument('--fixture-name')
    a=ap.parse_args()
    out={}
    if a.command=='build-default': out={'policy':build_default_policy().__dict__}
    elif a.command=='validate': out=validate_policy(build_default_policy())
    elif a.command=='inspect-fixture': out=_read(str(Path(a.fixtures_dir)/str(a.fixture_name)))
    else:
        payload=_read(a.input) if a.input else {}
        r=evaluate_capture_authorization(payload)
        out=r.to_dict()
    text=json.dumps(out,indent=2,sort_keys=True)
    if a.output: Path(a.output).write_text(text+'\n')
    print(text)
    return 1 if out.get('status','').startswith('capture_authorization_blocked') or out.get('status')=='capture_authorization_failed' else 0
if __name__=='__main__': raise SystemExit(main())
