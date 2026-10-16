import json, os, subprocess, sys
from pathlib import Path
from sentientos import maintenance_task_journal as j
from sentientos import maintenance_task_authority_lease as l
from sentientos import maintenance_commit_publication as m
from sentientos import maintenance_validation_controller as validation
from sentientos import maintenance_workspace_custody as custody
from sentientos import maintenance_local_codex_foreman as foreman
NOW='2026-08-05T00:00:00+0000'
def run(a,cwd): return subprocess.run(a,cwd=cwd,text=True,capture_output=True,check=True)
def repo(tmp_path, initial_files=None):
 r=tmp_path/'repo'; r.mkdir(); run(['git','init'],r); run(['git','config','user.email','a@b.test'],r); run(['git','config','user.name','A'],r); (r/'a.txt').write_text('one\n')
 for name,content in (initial_files or {}).items():
  path=r/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(content)
 run(['git','add','.'],r); run(['git','commit','-m','base'],r); base=run(['git','rev-parse','HEAD'],r).stdout.strip(); wt=tmp_path/'wt'; run(['git','worktree','add','--detach',str(wt),base],r); (wt/'a.txt').write_text('two\n'); return r,wt,base
def state(tmp_path): s=tmp_path/'state'; s.mkdir(); return s
def lease(task='task1',base='base',mode='pull_request'):
 d={'schema_version':l.LEASE_SCHEMA,'lease_id':'lease1','lease_digest':'','task_id':task,'candidate_id':'cand','candidate_revision_digest':'sha256:c','canonical_candidate_digest':'sha256:cc','candidate_set_digest':'sha256:cs','selection_digest':'sha256:ss','selector_policy_digest':'sha256:sp','operator_grant_id':'grant','operator_grant_digest':'sha256:g','repository_identity':'repo','base_sha':base,'objective_digest':'sha256:o','admitted_scope_digest':'sha256:s','admitted_subject_paths':['a.txt'],'forbidden_path_patterns':['.git/**'],'authority_classes':(['repository_commit','local_repository_base_advance'] if mode=='local_fast_forward_base_ref' else ['repository_commit','remote_repository_read','remote_ref_publish']+(['pull_request_publish'] if mode=='pull_request' else [])),'validation_expectations':['pytest'],'maximum_file_count':1,'maximum_changed_line_count':10,'maximum_implementation_seconds':1,'maximum_validation_seconds':1,'maximum_wall_clock_seconds':100,'maximum_attempts':1,'maximum_corrective_retries':0,'not_before':'2026','expires_at':'9999','grant_generation':'g','issued_at':'2026','lease_status':'active','reason_codes':[],'landing_terms':{'publication_mode':mode,'remote_name':'origin','base_ref':'refs/heads/main','head_ref_prefix':'sentientos/maintenance','commit_title':'[codex:sentientos] test objective','commit_identity_reference':'codex'}}; d['lease_digest']=l._seal(d,'lease_digest'); return d
def persist_lease(s, le): (s/'maintenance_leases').mkdir(exist_ok=True); (s/'maintenance_leases'/(le['lease_id']+'.json')).write_text(json.dumps(le,sort_keys=True,separators=(',',':'))+'\n')
def journal_ready(s,r,le):
 p={'candidate_ref':'cand','candidate_revision_digest':'sha256:c','canonical_candidate_digest':'sha256:cc','selection_digest':'sha256:ss','selector_policy_digest':'sha256:sp','admitted_scope_digest':'sha256:s','operator_grant_id':'grant','operator_grant_digest':'sha256:g','base_sha':le['base_sha'],'maximum_attempts':1,'maximum_corrective_retries':0}; j.append_event(s,'task_created',task_id=le['task_id'],payload=p,repo_root=r,repository_sha=le['base_sha'],recorded_at=NOW)
 j.append_event(s,'authority_lease_bound',task_id=le['task_id'],payload={'lease_id':le['lease_id'],'lease_digest':le['lease_digest'],'scope_digest':'sha256:s','expires_at':'9999','maximum_attempts':1,'maximum_corrective_retries':0},repo_root=r,recorded_at=NOW)
 j.append_event(s,'attempt_started',task_id=le['task_id'],payload={'attempt_id':'a1','lease_id':le['lease_id'],'scope_digest':'sha256:s'},repo_root=r,recorded_at=NOW)
 j.append_event(s,'implementation_completed',task_id=le['task_id'],payload={'attempt_id':'a1'},repo_root=r,recorded_at=NOW)
 j.append_event(s,'validation_started',task_id=le['task_id'],payload={'validation_ref_id':'v1','attempt_id':'a1','plan_digest':'sha256:vp','change_manifest_digest':'sha256:cm','worktree_descriptor_digest':'sha256:wt'},repo_root=r,recorded_at=NOW)
 j.append_event(s,'validation_passed',task_id=le['task_id'],payload={'validation_ref_id':'v1','attempt_id':'a1','result_digest':'sha256:vr'},repo_root=r,recorded_at=NOW)
def val(base,wt): return {'terminal_status':'validation_ready_for_commit','base_sha':base,'attempt_id':'a1','session_id':'s1','validation_ref_id':'v1','plan_digest':'sha256:vp','result_digest':'sha256:vr','change_manifest_digest':'sha256:cm','worktree_descriptor_digest':'sha256:wt','implementation_result_digest':'sha256:ir','changed_paths':['a.txt'],'worktree_manifest':m._manifest(Path(wt),['a.txt']),'patch_digest':'sha256:p','objective':'test objective'}
def pol(tmp_path,r): return m.seal_landing_policy({'policy_id':'p','repository_identity':'repo','canonical_repository_root':str(r),'external_state_root':str(tmp_path/'state'),'git_executable':'git','publication_client_executable':str(Path('tests/fixtures/fake_publication_client.py').resolve()),'commit_author_name':'Codex','commit_author_email':'codex@example.test','commit_committer_name':'Codex','commit_committer_email':'codex@example.test','commit_identity_reference':'codex','maximum_publication_attempts':2,'environment_name_allowlist':['PATH','HOME','TMPDIR','FAKE_PR_ROOT','FAKE_HEAD_SHA','FAKE_PR_MODE']})
def produce_validation(s, r, wt, le, *, at=NOW, initialize=True, execute=True, policy=None, expectations=None, session_id='s1'):
 """Fixture predecessors describe real files; validation custody is owner-produced."""
 le['validation_expectations']=expectations or ['git_diff_check']; le['lease_digest']=l._seal(le,'lease_digest'); persist_lease(s,le)
 if initialize:
  created={'base_sha':le['base_sha'],'admitted_scope_digest':le['admitted_scope_digest'],'maximum_attempts':le['maximum_attempts'],'maximum_corrective_retries':le['maximum_corrective_retries']}
  for kind,payload in [('task_created',created),('authority_lease_bound',{'lease_id':le['lease_id'],'lease_digest':le['lease_digest'],'scope_digest':le['admitted_scope_digest'],'expires_at':le['expires_at']}),('attempt_started',{'attempt_id':'a1','lease_id':le['lease_id'],'scope_digest':le['admitted_scope_digest']})]:
   assert j.append_event(s,kind,task_id=le['task_id'],payload=payload,repo_root=r,recorded_at=at).status=='event_appended'
 config=custody.WorkspaceCustodyConfig('fixture',le['repository_identity'],r,wt.parent,s,Path('/usr/bin/git'))
 descriptor={'schema_version':foreman.WORKTREE_SCHEMA,'task_id':le['task_id'],'session_id':session_id,'worktree_id':'fixture-worktree-'+session_id,'worktree_root':str(wt),'source_repository_root':str(r),'repository_identity':le['repository_identity'],'base_sha':le['base_sha'],'lease_id':le['lease_id'],'lease_digest':le['lease_digest']}
 descriptor['worktree_digest']=validation.seal(descriptor,'worktree_digest'); foreman.write_json(s/'maintenance_worktrees'/(session_id+'.json'),descriptor)
 manifest=custody.changed_manifest(config,le,descriptor)
 implementation={'schema_version':foreman.RESULT_SCHEMA,'status':'implementation_ready_for_validation','task_id':le['task_id'],'session_id':session_id,'codex_thread_id':'fixture-manual-implementation','worktree_descriptor_digest':descriptor['worktree_digest'],'change_manifest_digest':manifest['manifest_digest'],'patch_digest':manifest['patch_digest'],'changed_paths':manifest['changed_paths'],'invocation_digest':validation.dig({'fixture':'manual implementation','patch':manifest['patch_digest']})}
 implementation['result_digest']=validation.seal(implementation,'result_digest'); foreman.write_json(s/'maintenance_codex_results'/(session_id+'.json'),implementation)
 assert j.append_event(s,'implementation_completed',task_id=le['task_id'],payload={'attempt_id':'a1','session_id':session_id,'result_digest':implementation['result_digest']},repo_root=r,recorded_at=at).status=='event_appended'
 implementation.update(attempt_id='a1',attempt_ordinal=1,corrective_retry_ordinal=0)
 policy=policy or validation.ValidationPolicy('fixture',le['repository_identity'],git_executable='/usr/bin/git',external_scratch_root=str(s/'scratch'),per_command_default_ceiling_seconds=.5,terminal_reserve_seconds=.25)
 inputs=dict(state_root=s,repository_root=r,policy=policy,lease=le,implementation_result=implementation,worktree=descriptor,change_manifest=manifest,request={},session={},foreman_config=None,evaluation_time=at)
 if not execute: return inputs
 outcome=validation.advance_validation_controller(**inputs)
 assert outcome['status']=='validation_ready_for_commit',outcome
 return outcome['validation_result']

def setup(tmp_path, mode='pull_request'):
 r,wt,base=repo(tmp_path); s=state(tmp_path); le=lease(base=base,mode=mode)
 v=produce_validation(s,r,wt,le)
 return r,wt,s,le,v,pol(tmp_path,r)
