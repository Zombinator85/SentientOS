from pathlib import Path
from sentientos.maintenance_candidate import adapt_explicit_candidate, normalize_candidate_set
from sentientos.maintenance_candidate_selector import build_policy, select_candidate
from sentientos.maintenance_task_authority_lease import seal_grant, admit_selected_candidate, ACTION_REQUEST_SCHEMA
BASE='77b7d0a8bb7c3816a977c85082ddb8ed25273695'
NOW='2026-08-05T00:00:00+00:00'
EXP='2026-08-06T00:00:00+00:00'
def artifacts(state_root: Path, path='sentientos/example.py', auth=('code_edit','filesystem_write'), max_attempts=2):
    cand=adapt_explicit_candidate({'source_reference':'fixture','base_repository_sha':BASE,'objective':'bounded lease fixture','candidate_kind':'maintenance_loop','declared_subject_paths':[path],'declared_validation_expectations':['pytest fixture'],'evidence_references':['fixture:evidence'],'requested_authority_classes':auth,'estimated_file_count':1,'estimated_changed_line_count':10,'estimated_implementation_seconds':30,'estimated_validation_seconds':20}, base_repository_sha=BASE)
    cs=normalize_candidate_set([cand])
    policy=build_policy({'repository_base_sha':BASE,'allowed_path_prefixes':['sentientos','tests','docs/development'],'forbidden_path_patterns':['secrets/*'],'available_authority_classes':['proposal_selection_only','filesystem_read','filesystem_write','documentation_edit','test_edit','code_edit','governance_edit','journal_read','validation_execute','implementation_agent_session'],'maximum_file_count':5,'maximum_estimated_changed_lines':100,'maximum_implementation_seconds':300,'maximum_validation_seconds':300,'allowed_candidate_kinds':['maintenance_loop']})
    sel=select_candidate(cs,policy,journal_state_root=state_root)
    grant=seal_grant({'grant_id':'grant-fixture','operator_reference':'operator:fixture','approval_reference':'approval:fixture','repository_identity':'SentientOS','allowed_base_sha':BASE,'allowed_candidate_kinds':['maintenance_loop'],'allowed_path_prefixes':['sentientos','tests','docs/development'],'forbidden_path_patterns':['secrets/*'],'allowed_authority_classes':['proposal_selection_only','filesystem_read','filesystem_write','documentation_edit','test_edit','code_edit','governance_edit','journal_read','validation_execute','implementation_agent_session'],'maximum_file_count':5,'maximum_changed_line_count':100,'maximum_implementation_seconds':300,'maximum_validation_seconds':300,'maximum_wall_clock_seconds':3600,'maximum_attempts':max_attempts,'maximum_corrective_retries':1,'not_before':'2026-08-04T00:00:00+00:00','expires_at':EXP,'grant_generation':'gen-1','explicit_constraints':['metadata-only']})
    return cand,cs,sel,grant
def admitted(tmp_path: Path, **kw):
    c,cs,sel,g=artifacts(tmp_path, **kw); r=admit_selected_candidate(state_root=tmp_path,candidate_set=cs,selection=sel,operator_grant=g,evaluation_time=NOW,repo_root=Path.cwd()); return c,cs,sel,g,r
def action(lease, **kw):
    d={'schema_version':ACTION_REQUEST_SCHEMA,'task_id':lease['task_id'],'lease_id':lease['lease_id'],'candidate_revision_digest':lease['candidate_revision_digest'],'base_sha':lease['base_sha'],'action_kind':'metadata_check','requested_authority_classes':['code_edit'],'target_paths':['sentientos/example.py'],'planned_file_count':1,'planned_changed_lines':1,'planned_implementation_seconds':1,'planned_validation_seconds':1,'attempt_ordinal':1,'corrective_retry_ordinal':0}; d.update(kw); return d
