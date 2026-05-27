from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any
from sentientos.household_presence_camera_capture_denial_ledger import build_default_policy, evaluate_capture_denial_ledger, validate_policy

def _read(path:str)->dict[str,Any]:
    payload=json.loads(Path(path).read_text(encoding='utf-8'))
    return dict(payload) if isinstance(payload,dict) else {}

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument('command',choices=['build-default','evaluate','validate','summarize','inspect-fixture']); p.add_argument('--input'); p.add_argument('--fixtures-dir',default='tests/fixtures/household_presence_camera_capture_denial_ledger'); p.add_argument('--fixture-name'); p.add_argument('--output'); p.add_argument('--summary',action='store_true'); a=p.parse_args()
    out: dict[str, Any]
    if a.command=='build-default': out={'policy':build_default_policy().__dict__}
    elif a.command=='validate': out=validate_policy(build_default_policy())
    elif a.command=='inspect-fixture': out=_read(str(Path(a.fixtures_dir)/str(a.fixture_name)))
    else:
        payload=_read(a.input) if a.input else {}
        res=evaluate_capture_denial_ledger(payload)
        out=res.to_dict() if a.command=='evaluate' else {'status':str(res.status),'summary_counts':dict(res.report.summary_counts),'digest':str(res.ledger.digest)}
    text=json.dumps(out,indent=2,sort_keys=True); print(text)
    if a.output: Path(a.output).write_text(text+'\n',encoding='utf-8')
    return 1 if str(out.get('status','')).endswith(('invalid','failed','media_payload','external_authority')) else 0
if __name__=='__main__': raise SystemExit(main())
