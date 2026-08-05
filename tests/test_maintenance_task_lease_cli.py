import pytest
pytestmark = pytest.mark.no_legacy_skip

import json, subprocess, sys
from pathlib import Path
from tests.maintenance_lease_fixtures import artifacts, action, NOW
ROOT=Path.cwd()
def run(*a): return subprocess.run([sys.executable,'scripts/maintenance_task_authority_lease.py',*a],text=True,capture_output=True,cwd=ROOT)
def write(p,v): p.write_text(json.dumps(v)); return str(p)
def test_cli_grant_admit_verify_revoke_round_trip(tmp_path):
    c,cs,s,g=artifacts(tmp_path); cp=write(tmp_path/'cs.json',cs); sp=write(tmp_path/'sel.json',s); gp=write(tmp_path/'grant.json',g)
    assert run('verify-grant','--grant',gp,'--evaluation-time',NOW).returncode==0
    adm=run('admit','--state-root',str(tmp_path),'--candidate-set',cp,'--selection',sp,'--grant',gp,'--evaluation-time',NOW,'--repo-root','.')
    assert adm.returncode==0; data=json.loads(adm.stdout); lease=data['lease']; req=write(tmp_path/'req.json',action(lease))
    assert run('verify-lease','--state-root',str(tmp_path),'--lease-id',lease['lease_id'],'--evaluation-time',NOW,'--repo-root','.').returncode==0
    assert run('verify-action','--state-root',str(tmp_path),'--request',req,'--evaluation-time',NOW,'--repo-root','.').returncode==0
    assert run('revoke','--state-root',str(tmp_path),'--task-id',lease['task_id'],'--lease-id',lease['lease_id'],'--operator-revocation-reference','op:revoke','--evaluation-time',NOW,'--repo-root','.').returncode==0
    assert run('verify-action','--state-root',str(tmp_path),'--request',req,'--evaluation-time',NOW,'--repo-root','.').returncode!=0
    assert run('inspect','--state-root',str(tmp_path),'--lease-id',lease['lease_id'],'--repo-root','.').returncode==0
def test_cli_invalid_admission_returns_nonzero(tmp_path):
    c,cs,s,g=artifacts(tmp_path); s['result_status']='idle_no_viable_candidate'
    assert run('admit','--state-root',str(tmp_path),'--candidate-set',write(tmp_path/'cs.json',cs),'--selection',write(tmp_path/'sel.json',s),'--grant',write(tmp_path/'grant.json',g),'--evaluation-time',NOW,'--repo-root','.').returncode!=0
