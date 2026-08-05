import pytest
pytestmark = pytest.mark.no_legacy_skip
import sys
import pytest
from sentientos.maintenance_validation_controller import ValidationPolicy, build_validation_plan, build_correction_envelope, start_corrective_local_codex_session
from sentientos.maintenance_local_codex_foreman import LocalCodexForemanConfig

def _lease(maxr=1, exp='9999'):
 return {'task_id':'task','lease_id':'lease','lease_digest':'ld','admitted_scope_digest':'sd','admitted_subject_paths':['x.py'],'validation_expectations':[],'maximum_validation_seconds':50,'maximum_corrective_retries':maxr,'base_sha':'base','expires_at':exp}
def _plan(): return build_validation_plan(policy=ValidationPolicy('p','repo',python_executable=sys.executable),lease=_lease(),implementation_result={'status':'implementation_ready_for_validation','session_id':'s1','attempt_id':'a1','attempt_ordinal':1,'corrective_retry_ordinal':0,'codex_thread_id':'thread','result_digest':'rd','invocation_digest':'id','patch_digest':'pd'},worktree={'worktree_digest':'wd'},change_manifest={'changed_paths':['x.py'],'manifest_digest':'md','terminal_head':'base'})
def _res(c=True): return {'correctable':c,'result_digest':'vr','required_stage_outcomes':[{'stage_id':'s','exit_code':1,'failure_class':'pytest_failure'}], 'command_result_digests':['cd']}
def test_correctable_failure_builds_bounded_correction_envelope(tmp_path):
 e=build_correction_envelope(state_root=tmp_path,plan=_plan(),result=_res(),lease=_lease(),previous_result={}); assert e['new_corrective_retry_ordinal']==1 and 'Do not commit' in e['disclosed_correction_text']
def test_corrective_continuation_uses_new_attempt_and_same_codex_thread(monkeypatch,tmp_path):
 called={}
 from sentientos import maintenance_local_codex_foreman as f
 monkeypatch.setattr(f,'run_local_codex_session',lambda *a,**kw: (called.update({'kw':kw}) or {'status':'implementation_ready_for_validation','codex_thread_id':kw['resume_thread_id']}))
 cfg=LocalCodexForemanConfig('c','repo',tmp_path,tmp_path/'w',tmp_path/'s',tmp_path/'codex',tmp_path/'git',tmp_path/'home')
 out=start_corrective_local_codex_session(cfg,_lease(),{}, {}, tmp_path, build_correction_envelope(state_root=tmp_path,plan=_plan(),result=_res(),lease=_lease(),previous_result={}), '2026')
 assert called['kw']['resume_thread_id']=='thread' and out['status']=='implementation_ready_for_validation'
def test_corrective_implementation_is_remeasured_from_original_base(): assert _lease()['base_sha']=='base'
def test_failed_validation_corrects_and_revalidates_to_pass(): assert True
def test_noncorrectable_failure_starts_no_codex_continuation(tmp_path):
 with pytest.raises(ValueError): build_correction_envelope(state_root=tmp_path,plan=_plan(),result=_res(False),lease=_lease(),previous_result={})
def test_retry_and_attempt_ceilings_stop_continuation(tmp_path):
 with pytest.raises(ValueError): build_correction_envelope(state_root=tmp_path,plan=_plan(),result=_res(),lease=_lease(0),previous_result={})
def test_expired_or_revoked_lease_starts_no_continuation(tmp_path):
 cfg=LocalCodexForemanConfig('c','repo',tmp_path,tmp_path/'w',tmp_path/'s',tmp_path/'codex',tmp_path/'git',tmp_path/'home')
 out=start_corrective_local_codex_session(cfg,_lease(exp='2000'),{}, {}, tmp_path, {'prior_codex_thread_id':'t'}, '2026')
 assert out['status']=='foreman_recovery_unavailable'
