import pytest
pytestmark = pytest.mark.no_legacy_skip
from sentientos.maintenance_candidate import adapt_explicit_candidate, normalize_candidate_set, canonical_json_bytes
from sentientos.maintenance_candidate_selector import build_policy, select_candidate, selection_bytes
BASE='9c348f7b410a4bdf522b9973046e99ff825d1006'
def cand(obj='A', path='sentientos/a.py', sev='medium', rec=1, conf='medium', files=1, lines=1, auth=('proposal_selection_only',), kind='code'):
    return adapt_explicit_candidate({'source_reference':obj,'base_repository_sha':BASE,'objective':obj,'bounded_description':obj,'candidate_kind':kind,'severity':sev,'confidence':conf,'recurrence_count':rec,'declared_subject_paths':[path],'declared_validation_expectations':['pytest'],'evidence_references':[obj],'requested_authority_classes':list(auth),'declared_constraints':['bounded'],'estimated_file_count':files,'estimated_changed_line_count':lines,'estimated_implementation_seconds':60,'estimated_validation_seconds':60},base_repository_sha=BASE)
def pol(**kw):
    d={'repository_base_sha':BASE,'allowed_path_prefixes':['sentientos','docs'],'forbidden_path_patterns':[],'available_authority_classes':['proposal_selection_only'],'maximum_file_count':5,'maximum_estimated_changed_lines':100,'maximum_implementation_seconds':120,'maximum_validation_seconds':120,'allowed_candidate_kinds':['code']}; d.update(kw); return build_policy(d)
def sel(cs,p=None): return select_candidate(cs,p or pol())
def test_input_reordering_produces_identical_selection_bytes():
    a,b=cand('A'),cand('B','sentientos/b.py'); cs1=normalize_candidate_set([a,b]); cs2=normalize_candidate_set([b,a])
    assert selection_bytes(sel(cs1))==selection_bytes(sel(cs2))
def test_severity_recurrence_confidence_and_cost_ordering_is_deterministic():
    cs=normalize_candidate_set([cand('low',sev='low',rec=9,conf='confirmed'), cand('high',path='sentientos/h.py',sev='high',rec=1,conf='low')])
    assert sel(cs)['selected_candidate_summary']=='high'
def test_candidate_id_is_final_stable_tiebreaker():
    a,b=cand('A'),cand('B','sentientos/b.py'); cs=normalize_candidate_set([a,b]); ids=[x['candidate_id'] for x in cs['canonical_candidates']]; s=sel(cs); assert s['selected_candidate_id']==min(ids)
def test_forbidden_path_candidate_is_ineligible():
    s=sel(normalize_candidate_set([cand('A')]), pol(forbidden_path_patterns=['sentientos/*'])); assert 'candidate_path_forbidden' in next(iter(s['ineligible_candidate_ids'].values()))
def test_missing_authority_candidate_is_ineligible():
    s=sel(normalize_candidate_set([cand('A',auth=('code_edit',))])); assert 'candidate_authority_unavailable' in next(iter(s['ineligible_candidate_ids'].values()))
def test_budget_exceeding_candidate_is_ineligible():
    s=sel(normalize_candidate_set([cand('A',files=9)])); assert 'candidate_file_budget_exceeded' in next(iter(s['ineligible_candidate_ids'].values()))
def test_no_eligible_candidate_returns_durable_idle_status():
    assert sel(normalize_candidate_set([cand('A',path='other/a.py')]))['result_status']=='idle_no_viable_candidate'
