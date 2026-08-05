import json, subprocess, sys
from pathlib import Path
import pytest
from tests.maintenance_commit_publication_fixtures import setup,NOW
from tests.test_maintenance_publication_worker import bare
pytestmark=pytest.mark.no_legacy_skip
from sentientos import maintenance_commit_publication as m

def files(tmp_path, mode='pull_request'):
 r,w,s,l,v,p=setup(tmp_path,mode); vf=tmp_path/'v.json'; pf=tmp_path/'p.json'; vf.write_text(json.dumps(v,default=list)); pf.write_text(json.dumps(p)); return r,w,s,l,v,p,vf,pf
def call(r,w,s,l,vf,pf,cmd,*extra): return subprocess.run([sys.executable,'scripts/maintenance_commit_publication.py','--state-root',str(s),'--repository-root',str(r),'--worktree-root',str(w),'--task-id',l['task_id'],'--lease-id',l['lease_id'],'--validation-result',str(vf),'--landing-policy',str(pf),'--evaluation-time',NOW,*extra,cmd],text=True,capture_output=True)
def test_cli_commit_enqueue_publish_inspect_round_trip(tmp_path, monkeypatch):
 r,w,s,l,v,p,vf,pf=files(tmp_path); c=call(r,w,s,l,vf,pf,'commit'); assert c.returncode==0; pid=json.loads(c.stdout)['publication_request']['publication_id']; bare(tmp_path,r,v['base_sha']); monkeypatch.setenv('FAKE_PR_ROOT',str(tmp_path)); monkeypatch.setenv('FAKE_HEAD_SHA',json.loads(c.stdout)['commit_result']['commit_sha']); pub=subprocess.run([sys.executable,'scripts/maintenance_commit_publication.py','--state-root',str(s),'--repository-root',str(r),'--worktree-root',str(w),'--task-id',l['task_id'],'--lease-id',l['lease_id'],'--validation-result',str(vf),'--landing-policy',str(pf),'--evaluation-time',NOW,'--publication-id',pid,'publish-once'],text=True,capture_output=True); assert pub.returncode==0; ins=subprocess.run([sys.executable,'scripts/maintenance_commit_publication.py','--state-root',str(s),'--repository-root',str(r),'--task-id',l['task_id'],'--lease-id',l['lease_id'],'--landing-policy',str(pf),'--evaluation-time',NOW,'--publication-id',pid,'inspect-publication'],text=True,capture_output=True); assert ins.returncode==0
def test_cli_fast_forward_and_pull_request_modes(tmp_path):
 r,w,s,l,v,p,vf,pf=files(tmp_path,'fast_forward_base_ref'); c=call(r,w,s,l,vf,pf,'commit'); assert c.returncode==0
def test_cli_invalid_authority_or_remote_conflict_returns_nonzero(tmp_path):
 r,w,s,l,v,p,vf,pf=files(tmp_path); l['authority_classes']=[]; (s/'maintenance_leases'/(l['lease_id']+'.json')).write_text(json.dumps(l)); c=call(r,w,s,l,vf,pf,'plan-commit'); assert c.returncode!=0
