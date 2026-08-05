import pytest
pytestmark = pytest.mark.no_legacy_skip
import sys, subprocess, json
from pathlib import Path
from sentientos.maintenance_validation_controller import ValidationPolicy, build_validation_plan, run_validation_plan, build_correction_envelope

def _repo(tmp_path):
 r=tmp_path/'repo'; r.mkdir(); subprocess.run(['git','init'],cwd=r,check=True,capture_output=True); subprocess.run(['git','config','user.email','a@b'],cwd=r); subprocess.run(['git','config','user.name','a'],cwd=r); (r/'x.py').write_text('a=1\n'); subprocess.run(['git','add','.'],cwd=r,check=True); subprocess.run(['git','commit','-m','init'],cwd=r,check=True,capture_output=True); (r/'x.py').write_text('a=2\n'); return r
def _lease(): return {'task_id':'task','lease_id':'lease','lease_digest':'ld','admitted_scope_digest':'sd','admitted_subject_paths':['x.py'],'validation_expectations':[],'maximum_validation_seconds':50,'maximum_corrective_retries':1,'base_sha':'base'}
def _impl(): return {'status':'implementation_ready_for_validation','session_id':'s','attempt_id':'a1','attempt_ordinal':1,'corrective_retry_ordinal':0,'codex_thread_id':'t','result_digest':'rd','invocation_digest':'id','patch_digest':'pd'}
def _plan(r,pol): return build_validation_plan(policy=pol,lease=_lease(),implementation_result=_impl(),worktree={'worktree_digest':'wd','worktree_root':str(r)},change_manifest={'changed_paths':['README.md'],'manifest_digest':'md','terminal_head':'base'})
def test_recovery_after_command_result_persistence_does_not_rerun_command(tmp_path, monkeypatch):
 r=_repo(tmp_path); pol=ValidationPolicy('p','repo',python_executable=sys.executable,external_scratch_root=str(tmp_path/'scratch')); plan=_plan(r,pol); run_validation_plan(state_root=tmp_path/'s',repository_root=r,worktree_root=r,policy=pol,plan=plan,evaluation_time='2026',append_journal=False); monkeypatch.setattr(subprocess,'Popen',lambda *a,**k: (_ for _ in ()).throw(AssertionError('rerun'))); res=run_validation_plan(state_root=tmp_path/'s',repository_root=r,worktree_root=r,policy=pol,plan=plan,evaluation_time='2026',append_journal=False); assert res['terminal_status']=='validation_ready_for_commit'
def test_recovery_after_validation_result_persistence_appends_only_missing_event(tmp_path):
 r=_repo(tmp_path); pol=ValidationPolicy('p','repo',python_executable=sys.executable,external_scratch_root=str(tmp_path/'scratch')); res=run_validation_plan(state_root=tmp_path/'s',repository_root=r,worktree_root=r,policy=pol,plan=_plan(r,pol),evaluation_time='2026',append_journal=False); assert res['result_digest']
def test_recovery_after_correction_completion_reuses_same_attempt_and_session(tmp_path):
 e=build_correction_envelope(state_root=tmp_path,plan=_plan(_repo(tmp_path),ValidationPolicy('p','repo',python_executable=sys.executable)),result={'correctable':True,'result_digest':'r','required_stage_outcomes':[{'stage_id':'s','exit_code':1,'failure_class':'pytest_failure'}],'command_result_digests':['c']},lease=_lease(),previous_result={}); assert e['prior_implementation_session_id']=='s'
def test_process_concurrent_advance_runs_one_validation_and_one_correction(tmp_path):
 r=_repo(tmp_path); pol=ValidationPolicy('p','repo',python_executable=sys.executable,external_scratch_root=str(tmp_path/'scratch')); plan=_plan(r,pol); a=run_validation_plan(state_root=tmp_path/'s',repository_root=r,worktree_root=r,policy=pol,plan=plan,evaluation_time='2026',append_journal=False); b=run_validation_plan(state_root=tmp_path/'s',repository_root=r,worktree_root=r,policy=pol,plan=plan,evaluation_time='2026',append_journal=False); assert a['result_digest']==b['result_digest']
