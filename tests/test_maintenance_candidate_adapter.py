import pytest
pytestmark = pytest.mark.no_legacy_skip
from sentientos.maintenance_candidate import *
BASE='9c348f7b410a4bdf522b9973046e99ff825d1006'

def sig(artifact):
    return {'signal_id':'s1','source_kind':'mypy','finding_kind':'type_error','severity':'high','description':'Fix type error','subject_path':'sentientos/a.py','source_artifact':artifact,'evidence_refs':['e1'],'routing_eligible':True}

def explicit(**kw):
    d={'source_reference':'x','base_repository_sha':BASE,'objective':'Fix type error','bounded_description':'Fix type error','candidate_kind':'type_error','severity':'high','confidence':'confirmed','declared_subject_paths':['sentientos/a.py'],'declared_validation_expectations':['pytest a'],'evidence_references':['e2'],'requested_authority_classes':['proposal_selection_only'],'declared_constraints':['bounded']}
    d.update(kw); return d

def test_governed_signal_adapter_is_semantically_stable():
    a=adapt_governed_signal(sig('/tmp/a'),base_repository_sha=BASE); b=adapt_governed_signal({**sig('/tmp/b'),'observed_at':'now'},base_repository_sha=BASE)
    assert a.candidate_id==b.candidate_id and a.source_kind=='governed_improvement_signal'

def test_work_item_adapter_uses_declared_targets_not_prose():
    c=adapt_work_item_packet({'work_item_id':'w1','source_ref':'issue:1','title':'Edit docs','description_summary':'mentions sentientos/secret.py','requested_outcome':'done','declared_targets':['docs/x.md'],'declared_tests':['pytest t'],'declared_authority_requests':['proposal_selection_only'],'risk_class':'documentation_only','intake_status':'intake_accepted'},base_repository_sha=BASE)
    assert c.declared_subject_paths==('docs/x.md',)

def test_genesis_adapter_does_not_run_trial_or_adoption(monkeypatch):
    called=[]; monkeypatch.setattr('sentientos.genesis_forge.TrialRun', lambda *a,**k: called.append(1), raising=False)
    c=adapt_genesis_metadata({'proposal_id':'p','summary':'Need cap','need':{'capability':'cap','description':'Need cap','source':'telemetry'}},base_repository_sha=BASE)
    assert c.source_kind=='genesis_need' and not called and 'no_runtime_adoption' in c.declared_constraints

def test_semantic_duplicates_collapse_across_artifact_locations():
    cs=normalize_candidate_set([adapt_governed_signal(sig('/tmp/a'),base_repository_sha=BASE), adapt_governed_signal({**sig('/tmp/b'),'evidence_refs':['e2']},base_repository_sha=BASE)])
    assert len(cs['canonical_candidates'])==1 and cs['duplicate_groups']

def test_materially_conflicting_candidates_are_blocked():
    c1=adapt_explicit_candidate(explicit(),base_repository_sha=BASE); c2=adapt_explicit_candidate(explicit(severity='low'),base_repository_sha=BASE)
    cs=normalize_candidate_set([c1,c2])
    assert cs['contradictions'] and cs['canonical_candidates'][0]['lifecycle_disposition']=='candidate_contradicted'
