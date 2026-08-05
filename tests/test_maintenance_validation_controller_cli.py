import pytest
pytestmark = pytest.mark.no_legacy_skip
import json, subprocess, sys
from pathlib import Path
from sentientos.maintenance_validation_controller import ValidationPolicy

def _repo(tmp_path):
 r=tmp_path/'repo'; r.mkdir(); subprocess.run(['git','init'],cwd=r,check=True,capture_output=True); subprocess.run(['git','config','user.email','a@b'],cwd=r); subprocess.run(['git','config','user.name','a'],cwd=r); (r/'x.py').write_text('a=1\n'); subprocess.run(['git','add','.'],cwd=r,check=True); subprocess.run(['git','commit','-m','init'],cwd=r,check=True,capture_output=True); (r/'x.py').write_text('a=2\n'); return r
def _files(tmp_path,r):
 pol=ValidationPolicy('p','repo',python_executable=sys.executable,external_scratch_root=str(tmp_path/'scratch')).to_dict(); lease={'task_id':'task','lease_id':'lease','lease_digest':'ld','admitted_scope_digest':'sd','admitted_subject_paths':['x.py'],'validation_expectations':[],'maximum_validation_seconds':50,'maximum_corrective_retries':1,'base_sha':'base'}; impl={'status':'implementation_ready_for_validation','session_id':'s','attempt_id':'a1','attempt_ordinal':1,'corrective_retry_ordinal':0,'codex_thread_id':'t','result_digest':'rd','invocation_digest':'id','patch_digest':'pd'}; wt={'worktree_digest':'wd','worktree_root':str(r)}; cm={'changed_paths':['README.md'],'manifest_digest':'md','terminal_head':'base'}
 out=[]
 for name,obj in [('pol',pol),('lease',lease),('impl',impl),('wt',wt),('cm',cm)]: p=tmp_path/(name+'.json'); p.write_text(json.dumps(obj)); out.append(p)
 return out
def test_cli_plan_validate_advance_inspect_round_trip(tmp_path):
 r=_repo(tmp_path); pol,lease,impl,wt,cm=_files(tmp_path,r); base=[sys.executable,'scripts/maintenance_validation_controller.py']
 plan=subprocess.run(base+['plan','--state-root',str(tmp_path/'state'),'--repository-root',str(r),'--task-id','task','--evaluation-time','2026','--lease-id',str(lease),'--foreman-result',str(impl),'--validation-policy',str(pol),'--worktree-descriptor',str(wt),'--change-manifest',str(cm)],text=True,capture_output=True); assert plan.returncode==0
 pp=tmp_path/'plan.json'; pp.write_text(plan.stdout); val=subprocess.run(base+['validate','--state-root',str(tmp_path/'state'),'--repository-root',str(r),'--task-id','task','--evaluation-time','2026','--validation-policy',str(pol),'--worktree-descriptor',str(wt),'--plan',str(pp)],text=True,capture_output=True); assert val.returncode==0
 ins=subprocess.run(base+['inspect','--state-root',str(tmp_path/'state'),'--repository-root',str(r),'--task-id','task','--evaluation-time','2026'],text=True,capture_output=True); assert json.loads(ins.stdout)['status']=='inspect_ready'
def test_cli_failure_retry_limit_and_timeout_classifications(tmp_path):
 r=_repo(tmp_path); pol,lease,impl,wt,cm=_files(tmp_path,r); bad=json.loads(lease.read_text()); bad['maximum_validation_seconds']=1; lease.write_text(json.dumps(bad)); cp=subprocess.run([sys.executable,'scripts/maintenance_validation_controller.py','plan','--state-root',str(tmp_path/'state'),'--repository-root',str(r),'--task-id','task','--evaluation-time','2026','--lease-id',str(lease),'--foreman-result',str(impl),'--validation-policy',str(pol),'--worktree-descriptor',str(wt),'--change-manifest',str(cm)],text=True,capture_output=True); assert cp.returncode!=0
def test_cli_invalid_policy_or_identity_returns_nonzero(tmp_path):
 r=_repo(tmp_path); pol,lease,impl,wt,cm=_files(tmp_path,r); pol.write_text('{"schema_version":"bad"}'); cp=subprocess.run([sys.executable,'scripts/maintenance_validation_controller.py','plan','--state-root',str(tmp_path/'state'),'--repository-root',str(r),'--task-id','task','--evaluation-time','2026','--lease-id',str(lease),'--foreman-result',str(impl),'--validation-policy',str(pol),'--worktree-descriptor',str(wt),'--change-manifest',str(cm)],text=True,capture_output=True); assert cp.returncode!=0
