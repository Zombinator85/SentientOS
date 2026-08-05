import pytest
pytestmark = pytest.mark.no_legacy_skip
from sentientos.maintenance_candidate import adapt_explicit_candidate, normalize_candidate_set
from sentientos.maintenance_candidate_selector import build_policy, select_candidate, task_id_for_candidate
from sentientos.maintenance_task_journal import append_event
BASE='9c348f7b410a4bdf522b9973046e99ff825d1006'
def c(): return adapt_explicit_candidate({'source_reference':'x','base_repository_sha':BASE,'objective':'A','bounded_description':'A','candidate_kind':'code','declared_subject_paths':['sentientos/a.py'],'declared_validation_expectations':['pytest'],'evidence_references':['e'],'requested_authority_classes':['proposal_selection_only'],'declared_constraints':['bounded']},base_repository_sha=BASE)
def p(**kw):
    d={'repository_base_sha':BASE,'allowed_path_prefixes':['sentientos'],'forbidden_path_patterns':[],'available_authority_classes':['proposal_selection_only'],'maximum_file_count':5,'maximum_estimated_changed_lines':100,'maximum_implementation_seconds':120,'maximum_validation_seconds':120,'allowed_candidate_kinds':['code']}; d.update(kw); return build_policy(d)
def create(root,cand):
    append_event(root,'task_created',task_id=task_id_for_candidate(cand.candidate_id),payload={'candidate_ref':cand.candidate_id,'candidate_revision_digest':cand.candidate_revision_digest,'base_sha':BASE},repository_sha=BASE,repo_root='.')
def test_active_task_candidate_is_not_selected(tmp_path):
    orig=c(); cs=normalize_candidate_set([orig]); from sentientos.maintenance_candidate_selector import candidate_from_dict; cand=candidate_from_dict(cs['canonical_candidates'][0]); create(tmp_path,cand); s=select_candidate(cs,p(),journal_state_root=tmp_path)
    assert 'candidate_already_active' in s['ineligible_candidate_ids'][cand.candidate_id]
def test_closed_successful_task_candidate_is_resolved(tmp_path):
    orig=c(); cs=normalize_candidate_set([orig]); from sentientos.maintenance_candidate_selector import candidate_from_dict; cand=candidate_from_dict(cs['canonical_candidates'][0]); create(tmp_path,cand); append_event(tmp_path,'task_closed',task_id=task_id_for_candidate(cand.candidate_id),payload={'status':'success'},repo_root='.')
    s=select_candidate(cs,p(),journal_state_root=tmp_path)
    assert 'candidate_already_resolved' in s['ineligible_candidate_ids'][cand.candidate_id]
def test_cancelled_candidate_requires_explicit_reconsideration(tmp_path):
    orig=c(); cs=normalize_candidate_set([orig]); from sentientos.maintenance_candidate_selector import candidate_from_dict; cand=candidate_from_dict(cs['canonical_candidates'][0]); create(tmp_path,cand); append_event(tmp_path,'task_cancelled',task_id=task_id_for_candidate(cand.candidate_id),payload={},repo_root='.')
    s=select_candidate(cs,p(),journal_state_root=tmp_path)
    assert 'candidate_reconsideration_required' in s['ineligible_candidate_ids'][cand.candidate_id]
def test_unhealthy_journal_blocks_selection(tmp_path):
    orig=c(); cs=normalize_candidate_set([orig]); from sentientos.maintenance_candidate_selector import candidate_from_dict; cand=candidate_from_dict(cs['canonical_candidates'][0]); create(tmp_path,cand); f=tmp_path/'maintenance_tasks'/f'{task_id_for_candidate(cand.candidate_id)}.jsonl'; f.write_text(f.read_text()+'{"bad":')
    s=select_candidate(cs,p(),journal_state_root=tmp_path)
    assert s['result_status']=='journal_state_invalid'
