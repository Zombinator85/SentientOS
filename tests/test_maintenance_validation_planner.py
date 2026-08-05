import pytest
pytestmark = pytest.mark.no_legacy_skip
import sys
from pathlib import Path
import pytest
from sentientos.maintenance_validation_controller import ValidationPolicy, build_validation_plan, validate_expectation

def _lease(expect=()):
    return {'task_id':'task','lease_id':'lease','lease_digest':'ld','admitted_scope_digest':'sd','admitted_subject_paths':['sentientos/','docs/'],'validation_expectations':list(expect),'maximum_validation_seconds':100,'maximum_corrective_retries':1,'base_sha':'base'}
def _impl(): return {'status':'implementation_ready_for_validation','session_id':'sess','attempt_id':'att1','attempt_ordinal':1,'corrective_retry_ordinal':0,'codex_thread_id':'thread','result_digest':'rd','invocation_digest':'id','patch_digest':'pd'}
def _wt(): return {'worktree_digest':'wd','worktree_root':'/tmp/x'}
def _cm(paths): return {'changed_paths':paths,'manifest_digest':'md','terminal_head':'base'}
def _pol(**kw): return ValidationPolicy(policy_id='pol', repository_identity='repo', python_executable=sys.executable, **kw)

def test_same_inputs_produce_byte_identical_plan():
    kw=dict(policy=_pol(), lease=_lease(['pytest_node:tests/test_x.py::test_y']), implementation_result=_impl(), worktree=_wt(), change_manifest=_cm(['sentientos/x.py']), cycle_ordinal=1)
    assert build_validation_plan(**kw)==build_validation_plan(**kw)

def test_unknown_or_unsafe_expectation_is_rejected():
    with pytest.raises(ValueError): validate_expectation('shell:echo hi',[],[])
    with pytest.raises(ValueError): validate_expectation('pytest_node:',[],[])
    with pytest.raises(ValueError): validate_expectation('mypy_path:../x.py',['x.py'],['x.py'])
    with pytest.raises(ValueError): validate_expectation('pytest_node:tests/x.py::test_y|cat',[],[])

def test_python_docs_and_governance_paths_trigger_proportionate_stages():
    plan=build_validation_plan(policy=_pol(),lease=_lease(['pytest_node:tests/test_x.py::test_y']),implementation_result=_impl(),worktree=_wt(),change_manifest=_cm(['sentientos/maintenance_validation_controller.py','docs/development/maintenance_validation_controller.md']))
    kinds=[s['kind'] for s in plan['expanded_validation_stages']]
    assert kinds[:2]==['git_diff_check','pytest_node']
    for k in ['mypy_path','mypy_baseline','docs_check_deps','docs_build','prompt_boundaries','strict_audits','audit_immutability']: assert k in kinds

def test_ordinary_plan_starts_zero_exhaustive_matrix_processes():
    plan=build_validation_plan(policy=_pol(),lease=_lease(),implementation_result=_impl(),worktree=_wt(),change_manifest=_cm(['README.md']))
    assert plan['matrix_invocation_count']==0
    assert plan['exhaustive_matrix_status']=='not_requested_for_proportionate_validation'
    assert all('run_work_item_review_packet_matrix.py' not in ' '.join(s['argv']) for s in plan['expanded_validation_stages'])

def test_plan_cannot_exceed_lease_validation_budget():
    with pytest.raises(ValueError): build_validation_plan(policy=_pol(),lease={**_lease(), 'maximum_validation_seconds':1},implementation_result=_impl(),worktree=_wt(),change_manifest=_cm(['sentientos/x.py','docs/x.md']))
