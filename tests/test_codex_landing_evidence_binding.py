from __future__ import annotations
import json, os, subprocess
from pathlib import Path
import pytest

pytestmark = pytest.mark.no_legacy_skip
from sentientos.codex_landing_evidence_binding import *
from sentientos.landing_validation_plan import seal_validation_plan, verify_validation_plan

def git(repo: Path, *args: str):
    return subprocess.run(['git', *args], cwd=repo, check=True, text=True, capture_output=True).stdout.strip()

def repo(tmp_path: Path) -> Path:
    r=tmp_path/'r'; r.mkdir(); git(r,'init'); git(r,'config','user.email','a@b.c'); git(r,'config','user.name','A'); (r/'a.txt').write_text('base'); git(r,'add','.'); git(r,'commit','-m','base'); return r

def test_workspace_binding_deterministic_and_byte_invalidation(tmp_path: Path):
    r=repo(tmp_path); m=tmp_path/'m.json'; m.write_text('{"status":"passed","required_failure_count":0}')
    (r/'a.txt').write_text('one')
    b1=create_workspace_binding(r,intended_paths=['a.txt'],intended_commit_title='title',focused_test_commands=['python -m scripts.run_tests -q tests/x.py'],targeted_mypy_commands=['mypy x'],matrix_json_path=m)
    b2=create_workspace_binding(r,intended_paths=['./a.txt'],intended_commit_title='title',focused_test_commands=['python -m scripts.run_tests -q tests/x.py'],targeted_mypy_commands=['mypy x'],matrix_json_path=m)
    assert b1.changed_path_manifest_digest == b2.changed_path_manifest_digest
    (r/'a.txt').write_text('two')
    b3=create_workspace_binding(r,intended_paths=['a.txt'],intended_commit_title='title',matrix_json_path=m)
    assert b3.changed_path_manifest_digest != b1.changed_path_manifest_digest

def test_rejects_duplicate_traversal_git_unknown_runtime(tmp_path: Path):
    r=repo(tmp_path); (r/'a.txt').write_text('x')
    with pytest.raises(ValueError, match='canonical_duplicate_path'):
        create_workspace_binding(r,intended_paths=['a.txt','./a.txt'],intended_commit_title='t')
    with pytest.raises(ValueError, match='path_outside_repository'):
        create_workspace_binding(r,intended_paths=['../x'],intended_commit_title='t')
    with pytest.raises(ValueError, match='git_path_rejected'):
        create_workspace_binding(r,intended_paths=['.git/config'],intended_commit_title='t')
    (r/'b.txt').write_text('unknown')
    with pytest.raises(ValueError, match='unknown_dirty_paths'):
        create_workspace_binding(r,intended_paths=['a.txt'],intended_commit_title='t')
    with pytest.raises(ValueError, match='generated_runtime_path_rejected'):
        create_workspace_binding(r,intended_paths=['sentientos_data/vow/x.json'],intended_commit_title='t')

def test_symlink_deleted_and_commit_verification(tmp_path: Path):
    r=repo(tmp_path); m=tmp_path/'m.json'; m.write_text('{"status":"passed","required_failure_count":0}')
    (r/'link').symlink_to('a.txt'); os.remove(r/'a.txt')
    wb=create_workspace_binding(r,intended_paths=['link'],deleted_paths=['a.txt'],intended_commit_title='change',matrix_json_path=m)
    assert any(f.posture=='symlink' for f in wb.files) and any(f.posture=='deleted' for f in wb.files)
    git(r,'add','-A'); git(r,'commit','-m','change')
    cb=create_commit_binding(r,workspace_binding=wb,matrix_json_path=m)
    ok=verify_commit_matches_workspace(r, wb.to_dict(), cb.to_dict())
    assert ok.status=='landing_evidence_binding_ready'
    git(r,'commit','--allow-empty','-m','later')
    stale=verify_commit_matches_workspace(r, wb.to_dict(), cb.to_dict())
    assert 'current_head_changed_after_validation' in stale.reasons

def test_wrong_title_parent_matrix_and_runtime_root(tmp_path: Path):
    r=repo(tmp_path); m=tmp_path/'m.json'; m.write_text('{}'); (r/'a.txt').write_text('x')
    wb=create_workspace_binding(r,intended_paths=['a.txt'],intended_commit_title='wanted',matrix_json_path=m)
    git(r,'add','.'); git(r,'commit','-m','other')
    cb=create_commit_binding(r,workspace_binding=wb,matrix_json_path=m)
    res=verify_commit_matches_workspace(r, wb.to_dict(), cb.to_dict())
    assert 'commit_title_mismatch' in res.reasons
    m.write_text('{"changed":true}')
    cb2=create_commit_binding(r,workspace_binding=wb,matrix_json_path=m)
    assert 'matrix_digest_mismatch' in verify_commit_matches_workspace(r, wb.to_dict(), cb2.to_dict()).reasons
    with pytest.raises(ValueError, match='runtime_root_inside_workspace'):
        safe_runtime_roots(r, r/'tmp', 'id')

def test_body_binding_and_publication_classification(tmp_path: Path):
    body=tmp_path/'body.md'; body.write_text('### Motivation\n' + 'evidence '*100)
    art=tmp_path/'a.json'; art.write_text('{"ok":true}')
    commit={'head_sha':'h','tree_sha':'t','matrix_digest':'m'}
    side=create_body_binding('title', body, commit, {'artifact':str(art)}).to_dict()
    assert verify_body_binding('title', body, side, {'artifact':str(art)}).status=='pr_body_binding_ready'
    body.write_text(body.read_text()+'x')
    assert 'body_digest_mismatch' in verify_body_binding('title', body, side, {'artifact':str(art)}).reasons
    assert classify_publication_result({'title':'title','body':'...'}, {'title':'title'}).status=='publication_payload_echo_unverified'
    assert classify_publication_result({'pr_number':1,'url':'https://x'}, {}).status=='publication_identifier_observed'
    assert classify_publication_result({'repository':'r','base':'main','head_branch':'b','head_sha':'h'}, {'repository':'r','base':'main','head_branch':'b','head_sha':'h'}).status=='publication_head_binding_observed'
    assert classify_publication_result({'merged':True,'head_sha':'h'}, {'head_sha':'h'}).status=='publication_merge_observed'
    assert classify_publication_result({'head_sha':'bad'}, {'head_sha':'h'}).status=='publication_result_contradicted'

def publication_inputs(tmp_path: Path) -> tuple[dict[str, object], dict[str, Path]]:
    body=tmp_path/'body.md'; body.write_bytes(('### Motivation\n' + 'sealed evidence '*80).encode())
    pre=tmp_path/'pre.json'; post=tmp_path/'post.json'; guard=tmp_path/'guard.json'; binding=tmp_path/'binding.json'
    title='[codex:stabilization] fix publication handoff validation lineage'
    matrix_digest='f'*64
    common={'requested_profile':'exhaustive','effective_profile':'exhaustive','title':title,
            'intended_commit_title':title,'task_acceptance_manifest_digest':'d'*64,
            'task_acceptance_provenance_digest':'e'*64,
            'focused_test_command_contract':['python -m scripts.run_tests -q tests/test_codex_landing_evidence_binding.py'],
            'targeted_mypy_command_contract':['python -m mypy sentientos/codex_landing_evidence_binding.py'],
            'configured_total_budget_seconds':3600,'exhaustive_matrix_digest':matrix_digest}
    pre_plan=seal_validation_plan({**common,'repository_sha':'a'*40,'phase':'pre-commit',
        'changed_file_identity':['sentientos/codex_landing_evidence_binding.py'],
        'required_stage_ids':['focused_tests'],'conditionally_required_stage_ids':['docs_build'],
        'skipped_or_deferred_stage_ids':['docs_build'],
        'stage_results':{'focused_tests':{'status':'passed','duration_seconds':2}},
        'total_validation_duration_seconds':20,'remaining_budget_seconds':3580,
        'exhaustive_matrix_status':'matrix_reused','overall_status':'ready_to_commit'})
    post_plan=seal_validation_plan({**common,'repository_sha':'b'*40,'phase':'pr-metadata',
        'changed_file_identity':[],'required_stage_ids':['focused_tests','pr_landing_gate'],
        'conditionally_required_stage_ids':['docs_build'],'skipped_or_deferred_stage_ids':['docs_build','matrix_summary'],
        'stage_results':{'focused_tests':{'status':'passed','duration_seconds':3},'pr_landing_gate':{'status':'passed','duration_seconds':1}},
        'total_validation_duration_seconds':12,'remaining_budget_seconds':3588,
        'exhaustive_matrix_status':'matrix_reused','overall_status':'ready_for_pr_metadata'})
    assert pre_plan != post_plan
    assert verify_validation_plan(pre_plan)[0] and verify_validation_plan(post_plan)[0]
    workspace={'schema_version':'codex_landing_evidence_binding.v1','base_head_sha':'a'*40,
               'intended_commit_title':title,'changed_path_manifest_digest':'1'*64,'matrix_digest':matrix_digest}
    commit={'schema_version':'codex_landing_evidence_binding.v1','head_sha':'b'*40,'tree_sha':'c'*40,
            'parent_sha':'a'*40,'commit_subject':title,'changed_path_manifest_digest':'1'*64,
            'pre_commit_workspace_manifest_digest':'1'*64,'matrix_digest':matrix_digest}
    acceptance={'status':'task_acceptance_ready','manifest_digest':'d'*64,'provenance_digest':'e'*64}
    pre.write_text(json.dumps({'decision':{'status':'ready_to_commit'},'landing_validation_plan':pre_plan,'workspace_binding':workspace}))
    post.write_text(json.dumps({'decision':{'status':'ready_for_pr_metadata'},'landing_validation_plan':post_plan,'commit_binding':commit,'task_acceptance':acceptance}))
    guard.write_text(json.dumps({'status':'pr_metadata_guard_ready','proof':{'head_sha':commit['head_sha']}}))
    binding.write_text(json.dumps(create_body_binding(title,body,commit,{'pre':str(pre),'post':str(post),'guard':str(guard)}).to_dict()))
    inputs={'repository':'SentientOS/SentientOS','intended_base_ref':'main','body_path':body,'body_binding_path':binding,'pre_commit_finalizer_path':pre,'pr_metadata_finalizer_path':post,'pr_metadata_guard_path':guard}
    return inputs, {'body':body,'pre':pre,'post':post,'guard':guard,'binding':binding}

def test_distinct_phase_specific_validation_plans_seal_publication_handoff(tmp_path: Path):
    inputs, _ = publication_inputs(tmp_path)
    first=create_pr_publication_handoff(**inputs).to_dict(); second=create_pr_publication_handoff(**inputs).to_dict()
    assert first == second
    assert first['status']=='pr_publication_handoff_ready'
    assert first['schema_version']=='sentientos.pr_publication_handoff:v1'
    body=Path(inputs['body_path']).read_bytes()
    assert (first['body_sha256'],first['body_byte_length'])==(sha256_bytes(body),len(body))
    assert first['validation_profile']=='exhaustive' and first['exhaustive_matrix_status']=='matrix_reused'
    assert first['boundary']=={'publishes_pr':False,'observes_hosted_pr':False,'grants_network_authority':False}
    assert not any(word in first['status'] for word in ('published','hosted','github'))

@pytest.mark.parametrize(('target','field','value','reason'), [
    ('pre', 'artifact_digest', 'sha256:bad', 'pre_commit_validation_plan_invalid:validation_plan_digest_mismatch'),
    ('post', 'artifact_digest', 'sha256:bad', 'pr_metadata_validation_plan_invalid:validation_plan_digest_mismatch'),
])
def test_publication_handoff_rejects_invalid_phase_plan_digest(tmp_path: Path, target: str, field: str, value: str, reason: str):
    inputs, paths=publication_inputs(tmp_path); payload=json.loads(paths[target].read_text()); payload['landing_validation_plan'][field]=value; paths[target].write_text(json.dumps(payload))
    with pytest.raises(ValueError, match=reason): create_pr_publication_handoff(**inputs)

@pytest.mark.parametrize(('field','value'), [
    ('effective_profile','solo'), ('task_acceptance_manifest_digest','changed'),
    ('task_acceptance_provenance_digest','changed'), ('focused_test_command_contract',['pytest substituted']),
    ('targeted_mypy_command_contract',['mypy substituted']),
])
def test_publication_handoff_rejects_stable_validation_lineage_substitution(tmp_path: Path, field: str, value: object):
    inputs, paths=publication_inputs(tmp_path); post=json.loads(paths['post'].read_text()); post['landing_validation_plan'][field]=value; post['landing_validation_plan']=seal_validation_plan(post['landing_validation_plan']); paths['post'].write_text(json.dumps(post))
    with pytest.raises(ValueError, match=f'validation_lineage_field_mismatch:{field}'):
        create_pr_publication_handoff(**inputs)

@pytest.mark.parametrize(('target','field','value','reason'), [
    ('pre','phase','post-commit','pre_commit_validation_phase_invalid'),
    ('post','phase','post-commit','pr_metadata_validation_phase_invalid'),
    ('pre','repository_sha','9'*40,'pre_commit_validation_repository_sha_mismatch'),
    ('post','repository_sha','9'*40,'pr_metadata_validation_repository_sha_mismatch'),
])
def test_publication_handoff_rejects_phase_or_sha_transition_substitution(tmp_path: Path, target: str, field: str, value: str, reason: str):
    inputs, paths=publication_inputs(tmp_path); payload=json.loads(paths[target].read_text()); payload['landing_validation_plan'][field]=value; payload['landing_validation_plan']=seal_validation_plan(payload['landing_validation_plan']); paths[target].write_text(json.dumps(payload))
    with pytest.raises(ValueError, match=reason): create_pr_publication_handoff(**inputs)

@pytest.mark.parametrize(('target','field','value','reason'), [
    ('post','parent_sha','9'*40,'commit_parent_mismatch'),
    ('post','changed_path_manifest_digest','9'*64,'workspace_manifest_mismatch'),
    ('post','matrix_digest','9'*64,'matrix_digest_mismatch'),
])
def test_publication_handoff_rejects_commit_or_matrix_lineage_substitution(tmp_path: Path, target: str, field: str, value: str, reason: str):
    inputs, paths=publication_inputs(tmp_path); payload=json.loads(paths[target].read_text()); payload['commit_binding'][field]=value; paths[target].write_text(json.dumps(payload))
    with pytest.raises(ValueError, match=reason): create_pr_publication_handoff(**inputs)

def test_publication_handoff_accepts_digest_protected_phase_local_differences(tmp_path: Path):
    inputs, paths=publication_inputs(tmp_path); pre=json.loads(paths['pre'].read_text())['landing_validation_plan']; post=json.loads(paths['post'].read_text())['landing_validation_plan']
    for field in ('stage_results','required_stage_ids','skipped_or_deferred_stage_ids','total_validation_duration_seconds','remaining_budget_seconds','changed_file_identity','phase','repository_sha','overall_status'):
        assert pre[field] != post[field]
    assert create_pr_publication_handoff(**inputs).status == PUBLICATION_HANDOFF_READY

@pytest.mark.parametrize(('field','value'), [('repository','Other/repo'),('intended_base_ref','release')])
def test_publication_handoff_repository_and_base_substitution_fails(tmp_path: Path, field: str, value: str):
    inputs, _ = publication_inputs(tmp_path); sealed=create_pr_publication_handoff(**inputs).to_dict(); altered=dict(inputs); altered[field]=value
    assert verify_pr_publication_handoff(sealed, **altered).status=='pr_publication_handoff_blocked'

@pytest.mark.parametrize(('target','mutation'), [('body',lambda p:p.write_bytes(p.read_bytes()+b'x')),('binding',lambda p:p.write_text(p.read_text().replace('"body_byte_length": 1295','"body_byte_length": 1'))),('post',lambda p:p.write_text(p.read_text().replace('"head_sha": "'+('b'*40)+'"','"head_sha": "'+('f'*40)+'"'))),('guard',lambda p:p.write_text(p.read_text().replace('pr_metadata_guard_ready','blocked')))])
def test_publication_handoff_body_head_and_governing_evidence_substitution_fails(tmp_path: Path, target: str, mutation):
    inputs, paths = publication_inputs(tmp_path); sealed=create_pr_publication_handoff(**inputs).to_dict(); mutation(paths[target])
    assert verify_pr_publication_handoff(sealed, **inputs).status=='pr_publication_handoff_blocked'

@pytest.mark.parametrize(('target','old','new'), [('binding','[codex:stabilization] fix publication handoff validation lineage','alternate title'),('pre','"effective_profile": "exhaustive"','"effective_profile": "solo"'),('post','"parent_sha": "'+('a'*40)+'"','"parent_sha": "'+('9'*40)+'"'),('binding','"body_sha256": "','"body_sha256": "0')])
def test_publication_handoff_title_profile_base_and_digest_substitution_fails(tmp_path: Path, target: str, old: str, new: str):
    inputs, paths = publication_inputs(tmp_path); sealed=create_pr_publication_handoff(**inputs).to_dict(); paths[target].write_text(paths[target].read_text().replace(old,new))
    assert verify_pr_publication_handoff(sealed, **inputs).status=='pr_publication_handoff_blocked'

def hosted_case(tmp_path: Path, **changes: object):
    inputs, paths=publication_inputs(tmp_path); handoff=create_pr_publication_handoff(**inputs).to_dict()
    observation={'repository':handoff['repository'],'pr_number':7,'base_ref':handoff['intended_base_ref'],'base_sha':handoff['intended_base_sha'],'head_sha':handoff['intended_head_sha'],'head_tree_sha':handoff['intended_head_tree_sha'],'title':handoff['title'],'body_sha256':handoff['body_sha256'],'body_byte_length':handoff['body_byte_length'],'validation_profile':handoff['validation_profile'],'handoff_sha256':handoff['handoff_sha256'],'merge_state':'open','provenance':{'independent_hosted_observation':True,'publication_actuator_payload_echo':False,'source_kind':'operator_export'}}
    observation.update(changes)
    return inputs, paths, handoff, observation

def test_hosted_publication_exact_match_is_deterministic_and_merge_identity_is_separate(tmp_path: Path):
    inputs,paths,handoff,observation=hosted_case(tmp_path,merge_state='merged',merge_commit_sha='1'*40,merge_commit_tree_sha='2'*40)
    first=create_hosted_pr_publication_custody(handoff=handoff,observation=observation,hosted_body_path=paths['body'],**inputs).to_dict()
    second=create_hosted_pr_publication_custody(handoff=handoff,observation=observation,hosted_body_path=paths['body'],**inputs).to_dict()
    assert first==second and first['status']==HOSTED_PUBLICATION_EXACT and first['exact_publication_custody'] is True
    assert first['hosted_observation']['merge_commit_sha'] != first['hosted_observation']['head_sha']
    assert verify_hosted_pr_publication_custody(first,handoff=handoff,observation=observation,hosted_body_path=paths['body'],**inputs).status==HOSTED_PUBLICATION_EXACT

def test_pr_2066_rewritten_head_equal_tree_is_non_exact_custody_break(tmp_path: Path):
    inputs,paths,handoff,observation=hosted_case(tmp_path)
    handoff=dict(handoff); handoff['intended_head_sha']='131e27bb61ede5f59a02cb47b3fc8351d2b788f3'; handoff['intended_head_tree_sha']='0632acc46299a8fa69b8152788425cc244340d9f'
    # Authoritative governing inputs are represented by the fixture's rebuilt handoff.
    observation.update(head_sha='6cd5ec95c034a999de5a23f41969bd499f1f8b01',head_tree_sha=handoff['intended_head_tree_sha'],merge_state='merged',merge_commit_sha='205137c65c72c7732c60493dc7f199c2ffed1078',merge_commit_tree_sha=handoff['intended_head_tree_sha'])
    # Replace only fixture-local governing commit fields so verification still reconstructs them.
    post=json.loads(paths['post'].read_text()); post['commit_binding']['head_sha']=handoff['intended_head_sha']; post['commit_binding']['tree_sha']=handoff['intended_head_tree_sha']; post['landing_validation_plan']['repository_sha']=handoff['intended_head_sha']; post['landing_validation_plan']=seal_validation_plan(post['landing_validation_plan']); paths['post'].write_text(json.dumps(post))
    guard=json.loads(paths['guard'].read_text()); guard['proof']['head_sha']=handoff['intended_head_sha']; paths['guard'].write_text(json.dumps(guard))
    binding=json.loads(paths['binding'].read_text()); binding['commit_sha']=handoff['intended_head_sha']; binding['tree_sha']=handoff['intended_head_tree_sha']; binding['artifact_digests']={'pre':file_sha256(paths['pre']),'post':file_sha256(paths['post']),'guard':file_sha256(paths['guard'])}; paths['binding'].write_text(json.dumps(binding))
    handoff=create_pr_publication_handoff(**inputs).to_dict(); observation['handoff_sha256']=handoff['handoff_sha256']
    result=create_hosted_pr_publication_custody(handoff=handoff,observation=observation,hosted_body_path=paths['body'],**inputs)
    assert result.status==HOSTED_PUBLICATION_REWRITTEN and result.exact_publication_custody is False
    assert result.equivalence=={'head_sha_exact':False,'tree_equal':True,'parent_equal':None,'subject_equal':None}

@pytest.mark.parametrize(('field','value'), [('repository','elsewhere'),('base_ref','release'),('base_sha','0'*40),('head_tree_sha','9'*40),('title','changed'),('body_sha256','0'*64),('body_byte_length',1),('validation_profile','solo'),('handoff_sha256','0'*64)])
def test_hosted_publication_material_substitution_fails(tmp_path: Path, field: str, value: object):
    inputs,paths,handoff,observation=hosted_case(tmp_path,**{field:value})
    result=create_hosted_pr_publication_custody(handoff=handoff,observation=observation,hosted_body_path=paths['body'],**inputs)
    assert result.status==HOSTED_PUBLICATION_MISMATCH and not result.exact_publication_custody

def test_hosted_publication_requires_independent_observation_and_exact_body_bytes(tmp_path: Path):
    inputs,paths,handoff,observation=hosted_case(tmp_path,provenance={'independent_hosted_observation':False,'publication_actuator_payload_echo':True})
    result=create_hosted_pr_publication_custody(handoff=handoff,observation=observation,**inputs)
    assert result.status==HOSTED_PUBLICATION_INSUFFICIENT and not result.exact_publication_custody
    altered=tmp_path/'hosted-body.md'; altered.write_bytes(paths['body'].read_bytes()+b'x')
    assert create_hosted_pr_publication_custody(handoff=handoff,observation=observation,hosted_body_path=altered,**inputs).status==HOSTED_PUBLICATION_MISMATCH

def test_hosted_publication_substituted_handoff_and_artifact_fail_closed(tmp_path: Path):
    inputs,paths,handoff,observation=hosted_case(tmp_path); bad=dict(handoff); bad['repository']='other'
    with pytest.raises(ValueError,match='governing_handoff_not_verified'):
        create_hosted_pr_publication_custody(handoff=bad,observation=observation,hosted_body_path=paths['body'],**inputs)
    custody=create_hosted_pr_publication_custody(handoff=handoff,observation=observation,hosted_body_path=paths['body'],**inputs).to_dict(); custody['status']='forged'
    assert verify_hosted_pr_publication_custody(custody,handoff=handoff,observation=observation,hosted_body_path=paths['body'],**inputs).status==HOSTED_PUBLICATION_MISMATCH

def actuator_evidence(tmp_path: Path, *, evidence_class='declared_actuator_capability', identity=None, preservation=None, replacement=None, observations=None):
    identity=identity or {'id':'codex-hosted-publication-bridge','scope':'sentientos/operator-workcell/v1'}
    guarantees={key:True for key in ('repository_routing','intended_base_ref','intended_base_sha','exact_head_commit','head_tree','exact_title','exact_body_bytes')}
    guarantees.update({'branch_ref_identity':None,'branch_ref_relevant':False})
    if preservation: guarantees.update(preservation)
    replacements={key:False for key in ('synthesize','replay','cherry_pick','reauthor','recommit','normalize','otherwise_replace')}
    if replacement: replacements.update(replacement)
    path=tmp_path/'actuator.json'; path.write_text(json.dumps({'actuator_identity':identity,'evidence_class':evidence_class,'preservation_guarantees':guarantees,'commit_replacement':replacements,'historical_observations':observations or []},sort_keys=True))
    return path

def compatibility_case(tmp_path: Path, evidence: Path):
    inputs,_=publication_inputs(tmp_path); handoff=create_pr_publication_handoff(**inputs).to_dict()
    return inputs,handoff,create_publication_actuator_compatibility(handoff=handoff,actuator_evidence_path=evidence,**inputs)

def test_actuator_exact_compatibility_is_deterministic_verified_and_effect_free(tmp_path: Path, monkeypatch):
    evidence=actuator_evidence(tmp_path); inputs,handoff,first=compatibility_case(tmp_path,evidence)
    second=create_publication_actuator_compatibility(handoff=handoff,actuator_evidence_path=evidence,**inputs)
    assert first==second and first.status==ACTUATOR_EXACT_COMPATIBLE and first.exact_publication_compatible
    assert first.schema_version=='sentientos.publication_actuator_compatibility:v1'
    assert all(value is False for value in first.boundary.values())
    assert verify_publication_actuator_compatibility(first.to_dict(),handoff=handoff,actuator_evidence_path=evidence,**inputs).status==ACTUATOR_EXACT_COMPATIBLE

@pytest.mark.parametrize(('preservation','replacement'), [
    ({'exact_head_commit':None},None), ({'exact_body_bytes':False},None), ({'exact_title':None},None),
    ({'repository_routing':False},None), ({'intended_base_ref':None},None), ({'intended_base_sha':None},None),
    ({'branch_ref_relevant':True,'branch_ref_identity':None},None), ({'exact_head_commit':False},{'recommit':True}),
])
def test_actuator_incomplete_guarantees_never_become_compatible(tmp_path: Path, preservation, replacement):
    evidence=actuator_evidence(tmp_path,preservation=preservation,replacement=replacement)
    _,_,result=compatibility_case(tmp_path,evidence)
    expected=ACTUATOR_EXACT_HEAD_INCOMPATIBLE if replacement else ACTUATOR_CAPABILITY_INSUFFICIENT
    assert result.status==expected and not result.exact_publication_compatible

def test_actuator_contradictory_declaration_and_payload_echo_fail_closed(tmp_path: Path):
    evidence=actuator_evidence(tmp_path,replacement={'normalize':True})
    _,_,result=compatibility_case(tmp_path,evidence)
    assert result.status==ACTUATOR_MATERIAL_CONTRADICTION
    echo=actuator_evidence(tmp_path,evidence_class='payload_echo_self_report')
    _,_,result=compatibility_case(tmp_path,echo)
    assert result.status==ACTUATOR_CAPABILITY_INSUFFICIENT

@pytest.mark.parametrize(('intended','hosted','tree','merge'), [
    ('131e27bb61ede5f59a02cb47b3fc8351d2b788f3','6cd5ec95c034a999de5a23f41969bd499f1f8b01','0632acc46299a8fa69b8152788425cc244340d9f','205137c65c72c7732c60493dc7f199c2ffed1078'),
    ('3885a5b9bf9d1be8af7cc1a46638dd6259c0cae3','6835ce880697b4c8bac201f92fa456c812ca1418','62c3cadfce766158f17bc04411164179951092b8','d6b5b6ad7f96bc67a21e2fce7c5d266aed7ab3ee'),
])
def test_historical_equal_tree_rewrites_are_preflight_exact_head_incompatible(tmp_path: Path,intended,hosted,tree,merge):
    identity={'id':'codex-hosted-publication-bridge','scope':'sentientos/operator-workcell/v1'}
    observation={'actuator_identity':identity,'independent_hosted_observation':True,'publication_actuator_payload_echo':False,'intended_head_sha':intended,'hosted_head_sha':hosted,'intended_head_tree_sha':tree,'hosted_head_tree_sha':tree,'merge_commit_sha':merge}
    evidence=actuator_evidence(tmp_path,evidence_class='observed_actuator_behavior',identity=identity,preservation={key:None for key in ('repository_routing','intended_base_ref','intended_base_sha','exact_head_commit','head_tree','exact_title','exact_body_bytes')},replacement={key:None for key in ('synthesize','replay','cherry_pick','reauthor','recommit','normalize','otherwise_replace')},observations=[observation])
    _,_,result=compatibility_case(tmp_path,evidence)
    assert result.status==ACTUATOR_EXACT_HEAD_INCOMPATIBLE and result.historical_observations[0]['tree_equivalent'] is True

def test_other_actuator_history_not_generalized_and_substitutions_fail(tmp_path: Path):
    selected={'id':'bridge-a','scope':'tenant-a/workcell-v1'}; other={'id':'bridge-b','scope':'tenant-b/workcell-v1'}
    observation={'actuator_identity':other,'independent_hosted_observation':True,'publication_actuator_payload_echo':False,'intended_head_sha':'1'*40,'hosted_head_sha':'2'*40,'intended_head_tree_sha':'3'*40,'hosted_head_tree_sha':'3'*40}
    evidence=actuator_evidence(tmp_path,evidence_class='observed_actuator_behavior',identity=selected,observations=[observation])
    inputs,handoff,result=compatibility_case(tmp_path,evidence)
    assert result.status==ACTUATOR_CAPABILITY_INSUFFICIENT and not result.historical_observations[0]['applies_to_selected_actuator']
    sealed=result.to_dict(); evidence.write_text(evidence.read_text().replace('bridge-a','bridge-substituted'))
    assert verify_publication_actuator_compatibility(sealed,handoff=handoff,actuator_evidence_path=evidence,**inputs).status==ACTUATOR_MATERIAL_CONTRADICTION
    bad=dict(handoff); bad['repository']='substituted'
    assert verify_publication_actuator_compatibility(sealed,handoff=bad,actuator_evidence_path=evidence,**inputs).status==ACTUATOR_MATERIAL_CONTRADICTION

def test_unavailable_local_actuator_leaves_unobserved_hosted_state_unknown():
    report=publication_observer_scope(actuator_exposed_here=False,performed_by_this_execution=False)
    assert report['local_execution']['actuator_capability']=='actuator_not_exposed_here'
    assert report['local_execution']['publication_effect']=='publication_not_performed_by_this_execution'
    assert report['hosted_state']['classification']=='hosted_publication_not_observed'
    assert report['hosted_state']['remote_existence'] is None
    assert report['inference_boundaries']['unobserved_remote_state_is_unknown'] is True

def test_pr_2068_later_observation_advances_remote_knowledge_without_rewriting_local_facts():
    local=publication_observer_scope(actuator_exposed_here=False,performed_by_this_execution=False)
    observation={'pr_number':2068,'hosted_head_sha':'80a1765c081bc736c446782a670794f2d8227777',
                 'merge_commit_sha':'15eb5e4d2dd45547470a9cfc233eda480cb2b356','source_kind':'independent_hosted_observation'}
    later=publication_observer_scope(actuator_exposed_here=False,performed_by_this_execution=False,
                                     hosted_observation=observation,hosted_custody_verified=True)
    assert later['local_execution']==local['local_execution']
    assert later['hosted_state']['classification']=='hosted_publication_verified'
    assert later['hosted_state']['remote_existence'] is True
    assert later['hosted_state']['observation']==observation
