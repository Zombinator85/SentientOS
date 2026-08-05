import pytest
pytestmark = pytest.mark.no_legacy_skip

import multiprocessing as mp
from sentientos.maintenance_candidate_selector import build_policy, select_candidate
from sentientos import maintenance_task_journal as j
from tests.maintenance_lease_fixtures import artifacts, admitted, NOW, BASE
from sentientos.maintenance_task_authority_lease import admit_selected_candidate

def policy(): return build_policy({'repository_base_sha':BASE,'allowed_path_prefixes':['sentientos'],'forbidden_path_patterns':[],'available_authority_classes':['code_edit','filesystem_write'],'maximum_file_count':5,'maximum_estimated_changed_lines':100,'maximum_implementation_seconds':300,'maximum_validation_seconds':300,'allowed_candidate_kinds':['maintenance_loop']})
def test_selector_discovers_active_scope_bound_task(tmp_path):
    c,cs,s,g=artifacts(tmp_path); admit_selected_candidate(state_root=tmp_path,candidate_set=cs,selection=s,operator_grant=g,evaluation_time=NOW,repo_root='.')
    assert select_candidate(cs,policy(),journal_state_root=tmp_path)['result_status']=='idle_no_viable_candidate'
def test_selector_discovers_resolved_scope_bound_task(tmp_path):
    c,cs,s,g=artifacts(tmp_path); r=admit_selected_candidate(state_root=tmp_path,candidate_set=cs,selection=s,operator_grant=g,evaluation_time=NOW,repo_root='.'); j.append_event(tmp_path,'task_closed',task_id=r['task_id'],payload={'status':'success'},repo_root='.')
    assert 'candidate_already_resolved' in select_candidate(cs,policy(),journal_state_root=tmp_path)['ineligible_candidate_ids'][c.candidate_id]
def test_unknown_unhealthy_journal_blocks_selection(tmp_path):
    (tmp_path/'maintenance_tasks').mkdir(); (tmp_path/'maintenance_tasks'/'bad.jsonl').write_text('{bad')
    c,cs,s,g=artifacts(tmp_path)
    assert select_candidate(cs,policy(),journal_state_root=tmp_path)['result_status']=='journal_state_invalid'
def _worker(args):
    root,cs,s,g=args; return admit_selected_candidate(state_root=root,candidate_set=cs,selection=s,operator_grant=g,evaluation_time=NOW,repo_root='.')['status']
def test_process_concurrent_admission_has_one_task_and_one_lease(tmp_path):
    c,cs,s,g=artifacts(tmp_path)
    with mp.Pool(4) as pool: statuses=pool.map(_worker, [(str(tmp_path),cs,s,g)]*4)
    snaps=j.discover_maintenance_task_snapshots(tmp_path,repo_root='.')
    assert len([x for x in snaps if x['candidate_ref']==c.candidate_id])==1 and statuses.count('task_lease_ready')==1
def test_attempt_must_reference_active_lease_and_respect_attempt_limit(tmp_path):
    *_,r=admitted(tmp_path,max_attempts=1); lease=r['lease']
    bad=j.append_event(tmp_path,'attempt_started',task_id=lease['task_id'],payload={'attempt_id':'a0','lease_id':'other','scope_digest':lease['admitted_scope_digest']},repo_root='.')
    ok=j.append_event(tmp_path,'attempt_started',task_id=lease['task_id'],payload={'attempt_id':'a1','lease_id':lease['lease_id'],'scope_digest':lease['admitted_scope_digest']},repo_root='.')
    over=j.append_event(tmp_path,'attempt_started',task_id=lease['task_id'],payload={'attempt_id':'a2','lease_id':lease['lease_id'],'scope_digest':lease['admitted_scope_digest']},repo_root='.')
    assert bad.status=='transition_rejected' and ok.status=='event_appended' and over.status=='transition_rejected'
