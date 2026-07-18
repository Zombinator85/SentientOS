from __future__ import annotations
import pytest
pytestmark = pytest.mark.no_legacy_skip
import json, subprocess, sys, os
from pathlib import Path
from tests.test_host_fulfillment_authorization_runtime import fixtures

def write(p:Path,obj):
    p.write_text(json.dumps(obj.to_dict() if hasattr(obj,'to_dict') else obj), encoding='utf-8')

def test_cli_build_request_and_requires_apply(tmp_path: Path):
    issue,grant,ver,ledger,expiry,src,env=fixtures()
    paths=[]
    for name,obj in [('issue.json',issue),('grant.json',grant),('verification.json',ver),('ledger.json',ledger),('expiry.json',expiry)]:
        path=tmp_path/name; write(path,obj); paths.append(path)
    cmd=[sys.executable,'scripts/build_host_fulfillment_authorization_runtime.py','build-request','--issue-receipt',str(paths[0]),'--grant',str(paths[1]),'--verification',str(paths[2]),'--ledger',str(paths[3]),'--expiry',str(paths[4]),'--requested-time','2026-07-17T00:00:00+00:00','--not-before','2026-07-17T00:00:00+00:00','--not-after','2026-07-18T00:00:00+00:00']
    env={**os.environ, "PYTHONPATH":"."}
    out=subprocess.run(cmd,check=True,text=True,capture_output=True,env=env)
    req=tmp_path/'request.json'; req.write_text(out.stdout, encoding='utf-8')
    cmd2=[sys.executable,'scripts/build_host_fulfillment_authorization_runtime.py','consume','--runtime-root',str(tmp_path/'rt'),'--request',str(req),'--issue-receipt',str(paths[0]),'--grant',str(paths[1]),'--verification',str(paths[2]),'--ledger',str(paths[3]),'--expiry',str(paths[4])]
    out2=subprocess.run(cmd2,text=True,capture_output=True,env=env)
    assert out2.returncode in {3,4}
    assert ('not_applied' in out2.stdout) or ('denied' in out2.stdout)
