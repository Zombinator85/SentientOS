import pytest
pytestmark = pytest.mark.no_legacy_skip

from sentientos.maintenance_task_authority_lease import derive_lease, admit_selected_candidate, verify_action, revoke_lease, canonical_json_bytes
from tests.maintenance_lease_fixtures import artifacts, admitted, action, NOW
from sentientos import maintenance_task_journal as j

def test_lease_is_byte_deterministic(tmp_path):
    c,cs,s,g=artifacts(tmp_path); l1=derive_lease(c.to_dict(),cs,s,g,evaluation_time=NOW); l2=derive_lease(c.to_dict(),cs,s,g,evaluation_time=NOW)
    assert canonical_json_bytes(l1)==canonical_json_bytes(l2)
def test_lease_cannot_widen_grant_paths_authority_or_budgets(tmp_path):
    c,cs,s,g=artifacts(tmp_path); g['allowed_path_prefixes']=['docs']; g['grant_digest']='bad'
    r=admit_selected_candidate(state_root=tmp_path,candidate_set=cs,selection=s,operator_grant=g,evaluation_time=NOW,repo_root='.')
    assert r['status']=='task_lease_blocked'
def test_task_id_binds_candidate_revision_base_and_admitted_scope(tmp_path):
    c,cs,s,g=artifacts(tmp_path); l=derive_lease(c.to_dict(),cs,s,g,evaluation_time=NOW)
    assert l['task_id']==j.derive_task_id(candidate_ref=c.candidate_id,base_sha=c.base_repository_sha,contract_digest=c.candidate_revision_digest,admitted_scope_digest=l['admitted_scope_digest'])
def test_action_within_lease_is_accepted_without_execution(tmp_path):
    *_,r=admitted(tmp_path); assert verify_action(tmp_path, action(r['lease']), evaluation_time=NOW, repo_root='.')['status']=='action_within_lease'
def test_action_outside_path_authority_or_budget_is_denied(tmp_path):
    *_,r=admitted(tmp_path); lease=r['lease']
    assert verify_action(tmp_path, action(lease,target_paths=['other/x.py']), evaluation_time=NOW, repo_root='.')['status']=='action_denied_scope'
    assert verify_action(tmp_path, action(lease,requested_authority_classes=['governance_edit']), evaluation_time=NOW, repo_root='.')['status']=='action_denied_authority'
    assert verify_action(tmp_path, action(lease,planned_changed_lines=999), evaluation_time=NOW, repo_root='.')['status']=='action_denied_budget'
def test_revoked_or_expired_lease_denies_action(tmp_path):
    *_,r=admitted(tmp_path); lease=r['lease']
    assert verify_action(tmp_path, action(lease), evaluation_time='2026-08-07T00:00:00+00:00', repo_root='.')['status']=='action_denied_lease_expired'
    revoke_lease(tmp_path, task_id=lease['task_id'], lease_id=lease['lease_id'], operator_revocation_reference='op:revoke', evaluation_time=NOW, repo_root='.')
    assert verify_action(tmp_path, action(lease), evaluation_time=NOW, repo_root='.')['status']=='action_denied_lease_revoked'
