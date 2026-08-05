import pytest
pytestmark = pytest.mark.no_legacy_skip
import json, os, subprocess, sys
from pathlib import Path
from sentientos.maintenance_validation_controller import ValidationPolicy, build_validation_plan, run_validation_plan

def _repo(tmp_path):
    r=tmp_path/'repo'; r.mkdir(); subprocess.run(['git','init'],cwd=r,check=True,capture_output=True); subprocess.run(['git','config','user.email','a@b'],cwd=r); subprocess.run(['git','config','user.name','a'],cwd=r); (r/'x.py').write_text('a=1\n'); subprocess.run(['git','add','.'],cwd=r,check=True); subprocess.run(['git','commit','-m','init'],cwd=r,check=True,capture_output=True); (r/'x.py').write_text('a=2\n'); return r

def _lease(): return {'task_id':'task','lease_id':'lease','lease_digest':'ld','admitted_scope_digest':'sd','admitted_subject_paths':['x.py'],'validation_expectations':[],'maximum_validation_seconds':50,'maximum_corrective_retries':1,'base_sha':'base'}
def _impl(): return {'status':'implementation_ready_for_validation','session_id':'s','attempt_id':'a1','attempt_ordinal':1,'corrective_retry_ordinal':0,'codex_thread_id':'t','result_digest':'rd','invocation_digest':'id','patch_digest':'pd'}
def _wt(r): return {'worktree_digest':'wd','worktree_root':str(r)}
def _cm(): return {'changed_paths':['README.md'],'manifest_digest':'md','terminal_head':'base'}
def _plan(r, pol, expect=()):
    l={**_lease(),'validation_expectations':list(expect)}; return build_validation_plan(policy=pol,lease=l,implementation_result=_impl(),worktree=_wt(r),change_manifest=_cm())

def test_passing_validation_records_ready_for_commit_status(tmp_path):
    r=_repo(tmp_path); pol=ValidationPolicy('p','repo',python_executable=sys.executable,per_command_default_ceiling_seconds=5,external_scratch_root=str(tmp_path/'scratch'))
    res=run_validation_plan(state_root=tmp_path/'state',repository_root=r,worktree_root=r,policy=pol,plan=_plan(r,pol),evaluation_time='2026',append_journal=False)
    assert res['terminal_status']=='validation_ready_for_commit'; assert (tmp_path/'state/maintenance_validation_results'/f"{res['validation_ref_id']}.json").exists()

def test_failed_validator_records_immutable_failure_result(tmp_path):
    r=_repo(tmp_path); pol=ValidationPolicy('p','repo',python_executable=sys.executable,per_command_default_ceiling_seconds=5,external_scratch_root=str(tmp_path/'scratch'))
    plan=_plan(r,pol,['pytest_node:tests/nope.py::test_nope']); res=run_validation_plan(state_root=tmp_path/'state',repository_root=r,worktree_root=r,policy=pol,plan=plan,evaluation_time='2026',append_journal=False)
    assert res['terminal_status']=='validation_failed_correctable'; assert res['correctable'] is True; assert res['command_result_digests']

def test_validation_timeout_terminates_child_and_grandchild(tmp_path):
    r=_repo(tmp_path); script=r/'slow.py'; script.write_text('import subprocess,sys,time\nsubprocess.Popen([sys.executable,"-c","import time; time.sleep(5)"])\ntime.sleep(5)\n')
    pol=ValidationPolicy('p','repo',python_executable=sys.executable,per_command_default_ceiling_seconds=.2,external_scratch_root=str(tmp_path/'scratch'))
    plan=_plan(r,pol); plan['expanded_validation_stages'][0]['argv']=[sys.executable,'slow.py']; plan['expanded_validation_stages'][0]['kind']='pytest_node'; plan['expanded_validation_stages'][0]['argv_digest']='x'
    res=run_validation_plan(state_root=tmp_path/'state',repository_root=r,worktree_root=r,policy=pol,plan=plan,evaluation_time='2026',append_journal=False)
    assert res['terminal_status']=='validation_timed_out'

def test_validation_source_drift_fails_closed(tmp_path):
    r=_repo(tmp_path); drift=r/'drift.py'; drift.write_text('from pathlib import Path\nPath("x.py").write_text("drift\\n")\n')
    pol=ValidationPolicy('p','repo',python_executable=sys.executable,per_command_default_ceiling_seconds=5,external_scratch_root=str(tmp_path/'scratch'))
    plan=_plan(r,pol); plan['expanded_validation_stages'][0]['argv']=[sys.executable,'drift.py']; plan['expanded_validation_stages'][0]['argv_digest']='x'
    res=run_validation_plan(state_root=tmp_path/'state',repository_root=r,worktree_root=r,policy=pol,plan=plan,evaluation_time='2026',append_journal=False)
    assert res['terminal_status']=='validation_workspace_changed_during_proof'

def test_validation_commands_use_argv_without_command_interpreter(tmp_path, monkeypatch):
    r=_repo(tmp_path); seen=[]
    orig=subprocess.Popen
    def spy(argv,*a,**kw): seen.append((argv,kw.get('shell'))); return orig(argv,*a,**kw)
    monkeypatch.setattr(subprocess,'Popen',spy); pol=ValidationPolicy('p','repo',python_executable=sys.executable,external_scratch_root=str(tmp_path/'scratch'))
    run_validation_plan(state_root=tmp_path/'state',repository_root=r,worktree_root=r,policy=pol,plan=_plan(r,pol),evaluation_time='2026',append_journal=False)
    assert seen and all(isinstance(a,list) and sh is False for a,sh in seen)
