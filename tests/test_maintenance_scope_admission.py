import pytest
pytestmark = pytest.mark.no_legacy_skip

from pathlib import Path
from sentientos.maintenance_task_authority_lease import admit_selected_candidate
from sentientos import maintenance_task_journal as j
from tests.maintenance_lease_fixtures import artifacts, admitted, NOW

def counts(root, task_id):
    ev=j.replay_journal(j.journal_path_for(root,task_id,repo_root='.')).events
    return [e.event_type for e in ev]
def test_ready_selection_creates_task_and_binds_one_lease(tmp_path):
    *_,r=admitted(tmp_path); assert r['status']=='task_lease_ready'; assert counts(tmp_path,r['task_id']).count('task_created')==1; assert counts(tmp_path,r['task_id']).count('authority_lease_bound')==1
def test_tampered_selection_or_candidate_set_is_rejected(tmp_path):
    c,cs,s,g=artifacts(tmp_path); s['selected_candidate_id']='bad'
    assert admit_selected_candidate(state_root=tmp_path,candidate_set=cs,selection=s,operator_grant=g,evaluation_time=NOW,repo_root='.')['status']=='task_lease_blocked'
def test_exact_admission_retry_is_idempotent(tmp_path):
    c,cs,s,g=artifacts(tmp_path); r1=admit_selected_candidate(state_root=tmp_path,candidate_set=cs,selection=s,operator_grant=g,evaluation_time=NOW,repo_root='.'); r2=admit_selected_candidate(state_root=tmp_path,candidate_set=cs,selection=s,operator_grant=g,evaluation_time=NOW,repo_root='.')
    assert r2['status']=='task_lease_already_ready'; assert counts(tmp_path,r1['task_id']).count('task_created')==1
def test_interruption_after_task_creation_recovers_exact_lease(tmp_path):
    c,cs,s,g=artifacts(tmp_path); r1=admit_selected_candidate(state_root=tmp_path,candidate_set=cs,selection=s,operator_grant=g,evaluation_time=NOW,repo_root='.',interruption_point='after_task_created'); r2=admit_selected_candidate(state_root=tmp_path,candidate_set=cs,selection=s,operator_grant=g,evaluation_time=NOW,repo_root='.')
    assert r2['status']=='task_lease_recovered'; assert counts(tmp_path,r2['task_id']).count('authority_lease_bound')==1
def test_conflicting_lease_for_task_fails_closed(tmp_path):
    c,cs,s,g=artifacts(tmp_path); r=admit_selected_candidate(state_root=tmp_path,candidate_set=cs,selection=s,operator_grant=g,evaluation_time=NOW,repo_root='.'); p=tmp_path/'maintenance_leases'/f"{r['lease_id']}.json"; p.write_text('{"conflict":true}\n')
    assert admit_selected_candidate(state_root=tmp_path,candidate_set=cs,selection=s,operator_grant=g,evaluation_time=NOW,repo_root='.')['status']=='task_lease_conflict'
def test_admission_starts_zero_attempts(tmp_path):
    *_,r=admitted(tmp_path); assert r['snapshot']['active_attempt'] is None and r['snapshot']['completed_attempts']==[]
