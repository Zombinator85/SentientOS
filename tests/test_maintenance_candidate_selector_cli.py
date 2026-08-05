import pytest
pytestmark = pytest.mark.no_legacy_skip
import json, subprocess, sys
BASE='9c348f7b410a4bdf522b9973046e99ff825d1006'
def run(*a): return subprocess.run([sys.executable,'scripts/maintenance_candidate_selector.py',*a],text=True,capture_output=True)
def test_cli_adapt_normalize_select_round_trip(tmp_path):
    src=tmp_path/'s.json'; src.write_text(json.dumps({'signal_id':'s','source_kind':'mypy','finding_kind':'type_error','severity':'high','description':'Fix','subject_path':'sentientos/a.py','evidence_refs':['e']}))
    c=tmp_path/'c.json'; assert run('adapt','--source-kind','governed_improvement_signal','--input',str(src),'--base-sha',BASE,'--output',str(c)).returncode==0
    cs=tmp_path/'cs.json'; assert run('normalize','--input',str(c),'--output',str(cs)).returncode==0
    pol=tmp_path/'p.json'; pol.write_text(json.dumps({'repository_base_sha':BASE,'allowed_path_prefixes':['sentientos'],'forbidden_path_patterns':[],'available_authority_classes':['proposal_selection_only'],'maximum_file_count':5,'maximum_estimated_changed_lines':100,'maximum_implementation_seconds':120,'maximum_validation_seconds':120,'allowed_candidate_kinds':['type_error']}))
    out=run('select','--candidate-set',str(cs),'--policy',str(pol)); assert out.returncode==0 and json.loads(out.stdout)['result_status']=='ready_for_scope_admission'
def test_cli_idle_result_is_successful(tmp_path):
    cand=tmp_path/'c.json'; cand.write_text(json.dumps({'source_reference':'x','base_repository_sha':BASE,'objective':'A','candidate_kind':'code','declared_subject_paths':['other/a.py'],'requested_authority_classes':['proposal_selection_only'],'evidence_references':['e']}))
    cs=tmp_path/'cs.json'; run('normalize','--input',str(cand),'--output',str(cs))
    pol=tmp_path/'p.json'; pol.write_text(json.dumps({'repository_base_sha':BASE,'allowed_path_prefixes':['sentientos'],'forbidden_path_patterns':[],'available_authority_classes':['proposal_selection_only'],'maximum_file_count':5,'maximum_estimated_changed_lines':100,'maximum_implementation_seconds':120,'maximum_validation_seconds':120,'allowed_candidate_kinds':['code']}))
    out=run('select','--candidate-set',str(cs),'--policy',str(pol)); assert out.returncode==0 and json.loads(out.stdout)['result_status']=='idle_no_viable_candidate'
def test_cli_invalid_policy_returns_nonzero(tmp_path):
    cs=tmp_path/'cs.json'; cs.write_text(json.dumps({'schema_version':'sentientos.maintenance_candidate_set:v1','canonical_candidates':[],'aggregate_digest':'x'}))
    pol=tmp_path/'p.json'; pol.write_text(json.dumps({'bad':1}))
    assert run('select','--candidate-set',str(cs),'--policy',str(pol)).returncode!=0
