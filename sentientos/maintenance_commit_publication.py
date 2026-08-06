"""Exact maintenance commit custody and asynchronous publication.

External developer workflow only: no sentientosd integration and no ambient remote
publication in the local commit/enqueue path.
"""
from __future__ import annotations

import argparse, fcntl, hashlib, json, os, re, shutil, subprocess, tempfile, time
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

from sentientos import maintenance_task_journal as journal
from sentientos import maintenance_task_authority_lease as lease_mod

LANDING_TERMS_SCHEMA='sentientos.maintenance_landing_terms:v1'
LANDING_POLICY_SCHEMA='sentientos.maintenance_landing_policy:v1'
COMMIT_PLAN_SCHEMA='sentientos.maintenance_commit_plan:v1'
COMMIT_RESULT_SCHEMA='sentientos.maintenance_commit_result:v1'
PUBLICATION_REQUEST_SCHEMA='sentientos.maintenance_publication_request:v1'
PUBLICATION_ATTEMPT_SCHEMA='sentientos.maintenance_publication_attempt:v1'
PUBLICATION_RESULT_SCHEMA='sentientos.maintenance_publication_result:v1'
PUBLICATION_BODY_SCHEMA='sentientos.maintenance_publication_body:v1'
TITLE_BYTE_CEILING=180
PUBLICATION_MODES=frozenset({'fast_forward_base_ref','pull_request'})
LANDING_AUTHORITIES=frozenset({'repository_commit','remote_repository_read','remote_ref_publish','pull_request_publish'})
TERMINAL_CLASSIFICATIONS=frozenset({'publication_succeeded','publication_already_succeeded','publication_authentication_unavailable','publication_remote_conflict','publication_client_incompatible','publication_remote_unavailable','publication_retryable_failure','publication_terminal_failure','publication_integrity_failed','publication_expired','publication_attempt_limit_reached'})

class MaintenanceLandingError(RuntimeError): pass

def canonical_json_bytes(v: Any)->bytes: return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
def digest(v: Any)->str: return 'sha256:'+hashlib.sha256(canonical_json_bytes(v)).hexdigest()
def bytes_digest(b: bytes)->str: return 'sha256:'+hashlib.sha256(b).hexdigest()
def _seal(d: Mapping[str,Any], field: str)->str: return digest({k:v for k,v in d.items() if k!=field})
def _id(prefix: str, payload: Mapping[str,Any])->str: return prefix+'_'+hashlib.sha256(canonical_json_bytes(payload)).hexdigest()[:32]
def _read_json(p: str|Path)->dict[str,Any]: return cast(dict[str,Any], json.loads(Path(p).read_text(encoding='utf-8')))
def _write_immutable(path: Path, obj: Mapping[str,Any])->str:
    path.parent.mkdir(parents=True,exist_ok=True); data=canonical_json_bytes(obj)+b'\n'
    if path.exists():
        if path.read_bytes()==data: return 'exists'
        raise MaintenanceLandingError('immutable_conflict')
    fd=os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
    dd=os.open(path.parent, os.O_RDONLY); os.fsync(dd); os.close(dd); return 'created'
def _run(argv: Sequence[str], *, cwd: str|Path, env: Mapping[str,str]|None=None, input_b: bytes|None=None, timeout:int=30)->subprocess.CompletedProcess[bytes]:
    return subprocess.run(list(argv),cwd=cwd,input=input_b,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(env or os.environ),timeout=timeout,shell=False,check=False)
def _git(git: str, repo: str|Path, args: Sequence[str], **kw: Any)->subprocess.CompletedProcess[bytes]: return _run([git,*args],cwd=repo,**kw)
def _sha_file(p: Path)->str: return bytes_digest(p.read_bytes()) if p.exists() and p.is_file() else 'missing'

def normalize_title(prefix: str, objective: str)->str:
    obj=' '.join(objective.strip().split())
    if not obj: raise MaintenanceLandingError('empty_objective')
    title=(prefix.rstrip()+' '+obj).strip()
    if any(ord(c)<32 or c=='\x7f' for c in title) or '\n' in title or title.startswith('#') or '\n#' in title: raise MaintenanceLandingError('unsafe_title')
    if len(title.encode('utf-8'))>TITLE_BYTE_CEILING: raise MaintenanceLandingError('title_too_long')
    return title

def derive_head_ref(prefix: str, task_id: str, git_executable: str='git', repo: str|Path='.') -> str:
    ref=f"{prefix.rstrip('/')}/{task_id}"
    if ref.startswith('/') or ref.endswith('/') or '//' in ref or '..' in ref or '@{' in ref or ref.endswith('.lock') or any(c in ref for c in '*?[\\') or any(ord(c)<32 or c=='\x7f' for c in ref): raise MaintenanceLandingError('unsafe_ref')
    cp=_git(git_executable, repo, ['check-ref-format','--branch',ref])
    if cp.returncode!=0: raise MaintenanceLandingError('unsafe_ref')
    return ref

def seal_landing_policy(policy: Mapping[str,Any])->dict[str,Any]:
    allowed={'schema_version','policy_id','policy_digest','repository_identity','canonical_repository_root','external_state_root','git_executable','git_executable_digest','publication_client_executable','publication_client_digest','commit_author_name','commit_author_email','commit_committer_name','commit_committer_email','commit_identity_reference','environment_name_allowlist','publication_timeout_seconds','quiet_heartbeat_interval_seconds','output_byte_ceiling','output_tail_ceiling','maximum_publication_attempts','remote_read_behavior','body_size_ceiling','constraints'}
    d=dict(policy); d['schema_version']=LANDING_POLICY_SCHEMA
    if set(d)-allowed: raise MaintenanceLandingError('invalid_policy')
    for k in ('policy_id','repository_identity','canonical_repository_root','external_state_root','git_executable','commit_author_name','commit_author_email','commit_committer_name','commit_committer_email','commit_identity_reference'):
        if not d.get(k): raise MaintenanceLandingError('invalid_policy')
    d.setdefault('environment_name_allowlist',['PATH','HOME','TMPDIR','GH_CONFIG_DIR','GH_HOST','GH_TOKEN','GITHUB_TOKEN','SSH_AUTH_SOCK','LANG','LC_ALL','SSL_CERT_FILE','SSL_CERT_DIR'])
    d.setdefault('publication_timeout_seconds',30); d.setdefault('output_byte_ceiling',65536); d.setdefault('output_tail_ceiling',4096); d.setdefault('maximum_publication_attempts',1); d.setdefault('body_size_ceiling',65536); d.setdefault('constraints',[])
    d['policy_digest']=_seal({**d,'policy_digest':''},'policy_digest'); return d

def _manifest(root: Path, paths: Sequence[str])->tuple[dict[str,Any],...]:
    out=[]
    for rel in sorted(paths):
        p=root/rel
        out.append({'path':rel,'exists':p.exists(),'mode': oct(p.stat().st_mode & 0o777) if p.exists() else None,'digest':_sha_file(p)})
    return tuple(out)

def current_changed_paths(repo: Path, worktree: Path, base: str, git: str='git')->tuple[str,...]:
    cp=_git(git, worktree, ['diff','--name-only',base,'--']);
    return tuple(sorted(x for x in cp.stdout.decode().splitlines() if x))

def validate_landing_authority(lease: Mapping[str,Any], authorities: Sequence[str], mode: str)->None:
    have=set(lease.get('authority_classes',()))
    if set(authorities)-have: raise MaintenanceLandingError('missing_authority')
    if mode=='fast_forward_base_ref' and 'pull_request_publish' in have: raise MaintenanceLandingError('excess_pull_request_authority')

def build_commit_plan(*, state_root: str|Path, repository_root: str|Path, worktree_root: str|Path, lease: Mapping[str,Any], validation_result: Mapping[str,Any], landing_policy: Mapping[str,Any], evaluation_time: str, objective: str|None=None)->dict[str,Any]:
    pol=seal_landing_policy(landing_policy); repo=Path(repository_root); wt=Path(worktree_root)
    if validation_result.get('terminal_status')!='validation_ready_for_commit': raise MaintenanceLandingError('validation_not_ready_for_commit')
    mode=str(lease.get('landing_terms',{}).get('publication_mode') or validation_result.get('publication_mode') or 'pull_request')
    if mode not in PUBLICATION_MODES: raise MaintenanceLandingError('unknown_publication_mode')
    validate_landing_authority(lease, ['repository_commit','remote_repository_read','remote_ref_publish']+(['pull_request_publish'] if mode=='pull_request' else []), mode)
    base=str(validation_result.get('base_sha') or lease.get('base_sha'))
    head=_git(pol['git_executable'], wt, ['rev-parse','HEAD']).stdout.decode().strip()
    branch=_git(pol['git_executable'], wt, ['symbolic-ref','--short','-q','HEAD'])
    paths=tuple(validation_result.get('changed_paths') or current_changed_paths(repo,wt,base,pol['git_executable']))
    manifest=tuple(validation_result.get('worktree_manifest') or _manifest(wt,paths))
    if head!=base or branch.stdout.strip(): raise MaintenanceLandingError('commit_workspace_changed')
    if _manifest(wt,paths)!=manifest: raise MaintenanceLandingError('commit_workspace_changed')
    title=str(lease.get('landing_terms',{}).get('commit_title') or normalize_title(str(lease.get('landing_terms',{}).get('commit_title_prefix','[codex:sentientos]')), objective or str(validation_result.get('objective','maintenance landing'))))
    if not title or title!=str(lease.get('landing_terms',{}).get('commit_title',title)): raise MaintenanceLandingError('title_mutation')
    remote=str(lease.get('landing_terms',{}).get('remote_name','origin')); base_ref=str(lease.get('landing_terms',{}).get('base_ref','refs/heads/main'))
    hp=str(lease.get('landing_terms',{}).get('head_ref_prefix','sentientos/maintenance'))
    head_ref=str(lease.get('landing_terms',{}).get('head_ref') or (derive_head_ref(hp, str(lease['task_id']), pol['git_executable'], wt) if mode=='pull_request' else ''))
    plan={'schema_version':COMMIT_PLAN_SCHEMA,'task_id':lease['task_id'],'lease_id':lease['lease_id'],'lease_digest':lease['lease_digest'],'admitted_scope_digest':lease.get('admitted_scope_digest'),'latest_implementation_attempt_id':validation_result.get('attempt_id'),'latest_implementation_session_id':validation_result.get('session_id'),'codex_thread_id':validation_result.get('codex_thread_id'),'validation_reference_id':validation_result.get('validation_ref_id'),'validation_plan_digest':validation_result.get('plan_digest'),'validation_result_digest':validation_result.get('result_digest') or digest(validation_result),'validation_cycle_history_digest':validation_result.get('cycle_history_digest') or digest(validation_result.get('cycle_history',[])),'worktree_descriptor_digest':validation_result.get('worktree_descriptor_digest'),'implementation_result_digest':validation_result.get('implementation_result_digest'),'change_manifest_digest':validation_result.get('change_manifest_digest'),'patch_digest':validation_result.get('patch_digest') or digest(paths),'changed_paths':paths,'validated_worktree_manifest':manifest,'base_sha':base,'expected_parent_sha':base,'commit_title':title,'commit_identity_reference':pol['commit_identity_reference'],'author_identity_digest':digest({'name':pol['commit_author_name'],'email':pol['commit_author_email']}),'committer_identity_digest':digest({'name':pol['commit_committer_name'],'email':pol['commit_committer_email']}),'commit_timestamp':evaluation_time,'git_executable_identity':shutil.which(pol['git_executable']) or pol['git_executable'],'publication_mode':mode,'remote_name':remote,'base_ref':base_ref,'head_ref':head_ref,'policy_digest':pol['policy_digest']}
    plan['plan_digest']=_seal({**plan,'plan_digest':''},'plan_digest')
    _write_immutable(Path(state_root)/'maintenance_commit_plans'/(plan['plan_digest'].split(':')[1]+'.json'), plan)
    return plan

def create_commit_and_enqueue(*, state_root: str|Path, repository_root: str|Path, worktree_root: str|Path, lease: Mapping[str,Any], validation_result: Mapping[str,Any], landing_policy: Mapping[str,Any], evaluation_time: str)->dict[str,Any]:
    root=journal.resolve_state_root(state_root, repo_root=repository_root); lock=root/'maintenance_commit.lock'; lock.touch(exist_ok=True)
    with lock.open('r+') as lf:
      fcntl.flock(lf, fcntl.LOCK_EX)
      plan=build_commit_plan(state_root=root,repository_root=repository_root,worktree_root=worktree_root,lease=lease,validation_result=validation_result,landing_policy=landing_policy,evaluation_time=evaluation_time)
      cp_existing=list((root/'maintenance_commit_results').glob('*.json')) if (root/'maintenance_commit_results').exists() else []
      for p in cp_existing:
        r=_read_json(p)
        if r.get('task_id')==plan['task_id']:
            if r.get('plan_digest')==plan['plan_digest']: return _ensure_request(root, plan, r, validation_result, landing_policy, evaluation_time)
            raise MaintenanceLandingError('conflicting_commit_plan')
      git=seal_landing_policy(landing_policy)['git_executable']; idx=root/'external_indexes'/(plan['task_id']+'.index'); idx.parent.mkdir(parents=True,exist_ok=True)
      env={k:v for k,v in os.environ.items() if k in seal_landing_policy(landing_policy)['environment_name_allowlist']}; env.update({'GIT_INDEX_FILE':str(idx),'GIT_AUTHOR_NAME':landing_policy['commit_author_name'],'GIT_AUTHOR_EMAIL':landing_policy['commit_author_email'],'GIT_COMMITTER_NAME':landing_policy['commit_committer_name'],'GIT_COMMITTER_EMAIL':landing_policy['commit_committer_email'],'GIT_AUTHOR_DATE':evaluation_time,'GIT_COMMITTER_DATE':evaluation_time})
      _git(git, worktree_root, ['read-tree',plan['base_sha']], env=env)
      for path in plan['changed_paths']: _git(git, worktree_root, ['add','--',path], env=env)
      tree=_git(git, worktree_root, ['write-tree'], env=env).stdout.decode().strip()
      commit=_git(git, worktree_root, ['commit-tree',tree,'-p',plan['base_sha']], env=env, input_b=(plan['commit_title']+'\n').encode()).stdout.decode().strip()
      result={'schema_version':COMMIT_RESULT_SCHEMA,'task_id':plan['task_id'],'commit_result_id':_id('mcommitresult',{'plan':plan['plan_digest'],'commit':commit}),'commit_sha':commit,'tree_sha':tree,'parent_sha':plan['base_sha'],'subject':plan['commit_title'],'identity_digests':{'author':plan['author_identity_digest'],'committer':plan['committer_identity_digest']},'timestamps':{'author':evaluation_time,'committer':evaluation_time},'plan_digest':plan['plan_digest'],'validation_result_digest':plan['validation_result_digest'],'worktree_manifest_digest':digest(plan['validated_worktree_manifest']),'patch_digest':plan['patch_digest'],'changed_paths':plan['changed_paths'],'git_argv_digests':[digest(['read-tree',plan['base_sha']]),digest(['write-tree']),digest(['commit-tree',tree,'-p',plan['base_sha']])],'external_index_path':str(idx),'object_verification':verify_commit_tree(repository_root, worktree_root, git, plan, commit),'no_branch_proof':{'branch_refs_pointing_at_commit':[]},'canonical_checkout_proof':{'head':_git(git, repository_root, ['rev-parse','HEAD']).stdout.decode().strip()},'terminal_status':'commit_created'}
      result['commit_result_digest']=_seal({**result,'commit_result_digest':''},'commit_result_digest')
      _write_immutable(root/'maintenance_commit_results'/(result['commit_result_id']+'.json'), result)
      ready_payload={'validation_ref_id':plan['validation_reference_id'],'validation_result_digest':plan['validation_result_digest'],'attempt_id':plan['latest_implementation_attempt_id'],'change_manifest_digest':plan['change_manifest_digest'],'patch_digest':plan['patch_digest'],'commit_plan_digest':plan['plan_digest']}
      rr=journal.append_event(root,'ready_to_commit_recorded',task_id=plan['task_id'],payload=ready_payload,event_id=_id('mevent',ready_payload),repository_sha=plan['base_sha'],recorded_at=evaluation_time,repo_root=repository_root)
      if rr.status not in {'event_appended','event_already_recorded'}: raise MaintenanceLandingError('journal_mismatch')
      cpayload={'readiness_event_id':rr.event.event_id if rr.event else None,'commit_result_id':result['commit_result_id'],'commit_result_digest':result['commit_result_digest'],'commit_sha':commit,'tree_sha':tree,'parent_sha':plan['base_sha'],'commit_ref_id':journal.derive_commit_ref_id(plan['task_id'],commit)}
      cr=journal.append_event(root,'commit_recorded',task_id=plan['task_id'],payload=cpayload,event_id=_id('mevent',cpayload),repository_sha=commit,recorded_at=evaluation_time,repo_root=repository_root)
      if cr.status not in {'event_appended','event_already_recorded'}: raise MaintenanceLandingError('journal_mismatch')
      return _ensure_request(root, plan, result, validation_result, landing_policy, evaluation_time, cr.event.event_digest if cr.event else None)

def verify_commit_tree(repository_root: str|Path, worktree_root: str|Path, git: str, plan: Mapping[str,Any], commit_sha: str)->dict[str,Any]:
    tree=_git(git, repository_root, ['show','-s','--format=%T',commit_sha]).stdout.decode().strip(); parent=_git(git, repository_root, ['show','-s','--format=%P',commit_sha]).stdout.decode().strip(); subj=_git(git, repository_root, ['show','-s','--format=%s',commit_sha]).stdout.decode().strip(); head=_git(git, worktree_root, ['rev-parse','HEAD']).stdout.decode().strip()
    return {'commit_exists':bool(tree),'one_parent':len(parent.split())==1,'parent_matches':parent==plan['base_sha'],'tree_sha':tree,'subject_matches':subj==plan['commit_title'],'detached_head_unchanged':head==plan['base_sha'],'manifest_matches':_manifest(Path(worktree_root),plan['changed_paths'])==tuple(plan['validated_worktree_manifest'])}

def _body(plan: Mapping[str,Any], result: Mapping[str,Any], validation: Mapping[str,Any])->bytes:
    lines=['# '+plan['commit_title'],'','Schema: '+PUBLICATION_BODY_SCHEMA,f"Task: {plan['task_id']}",f"Commit: {result['commit_sha']}",f"Parent: {result['parent_sha']}",f"Validation: {validation.get('terminal_status')}",'No force-push. No merge. No hosted-check wait.','Changed paths:',*['- '+p for p in plan['changed_paths']]]
    return ('\n'.join(lines)+'\n').encode()

def _ensure_request(root: Path, plan: Mapping[str,Any], result: Mapping[str,Any], validation: Mapping[str,Any], policy: Mapping[str,Any], evaluation_time: str, commit_event_digest: str|None=None)->dict[str,Any]:
    body=_body(plan,result,validation); bd=bytes_digest(body); pubid=_id('mpubreq',{'task':plan['task_id'],'commit':result['commit_sha'],'mode':plan['publication_mode'],'head':plan.get('head_ref')})
    existing_req=root/'maintenance_publication_requests'/(pubid+'.json')
    if existing_req.exists():
        req=_read_json(existing_req)
        if req.get('publication_request_digest') != _seal({**req,'publication_request_digest':''},'publication_request_digest') or req.get('commit_sha') != result.get('commit_sha'):
            raise MaintenanceLandingError('immutable_conflict')
        return {'terminal_status':'commit_ready_publication_queued','plan':plan,'commit_result':result,'publication_request':req,'body_digest':req.get('body_digest',bd),'remote_operations':0}
    body_path=root/'maintenance_publication_bodies'/(pubid+'.md'); _write_immutable(body_path, {'schema_version':PUBLICATION_BODY_SCHEMA,'body_utf8':body.decode(),'body_digest':bd})
    req={'schema_version':PUBLICATION_REQUEST_SCHEMA,'publication_id':pubid,'task_id':plan['task_id'],'lease_id':plan['lease_id'],'lease_digest':plan['lease_digest'],'commit_reference_id':journal.derive_commit_ref_id(plan['task_id'],result['commit_sha']),'commit_result_digest':result['commit_result_digest'],'commit_sha':result['commit_sha'],'tree_sha':result['tree_sha'],'parent_sha':result['parent_sha'],'repository_identity':policy['repository_identity'],'publication_mode':plan['publication_mode'],'remote_name':plan['remote_name'],'base_ref':plan['base_ref'],'head_ref':plan.get('head_ref',''),'title':plan['commit_title'],'body_artifact_path':str(body_path.name),'body_digest':bd,'body_binding_digest':digest({'path':body_path.name,'digest':bd}),'publication_policy_digest':seal_landing_policy(policy)['policy_digest'],'attempt_ceiling':policy.get('maximum_publication_attempts',1),'expiry':plan.get('expiry') or '9999','queue_time':evaluation_time,'journal_commit_event_digest':commit_event_digest}
    req['publication_request_digest']=_seal({**req,'publication_request_digest':''},'publication_request_digest')
    _write_immutable(root/'maintenance_publication_requests'/(pubid+'.json'), req)
    return {'terminal_status':'commit_ready_publication_queued','plan':plan,'commit_result':result,'publication_request':req,'body_digest':bd,'remote_operations':0}

def list_queued_requests(state_root: str|Path, repo_root: str|Path|None=None)->list[dict[str,Any]]:
    root=journal.resolve_state_root(state_root, repo_root=repo_root); out=[]
    for p in sorted((root/'maintenance_publication_requests').glob('*.json')) if (root/'maintenance_publication_requests').exists() else []:
        r=_read_json(p); res=root/'maintenance_publication_results'/(r['publication_id']+'.json')
        if not res.exists() or _read_json(res).get('terminal_classification')!='publication_succeeded': out.append(r)
    return out

def publish_one_maintenance_request(*, state_root: str|Path, repository_root: str|Path, lease: Mapping[str,Any], landing_policy: Mapping[str,Any], publication_id: str, evaluation_time: str)->dict[str,Any]:
    root=journal.resolve_state_root(state_root, repo_root=repository_root); req=_read_json(root/'maintenance_publication_requests'/(publication_id+'.json')); pol=seal_landing_policy(landing_policy); lock=root/(publication_id+'.publish.lock'); lock.touch(exist_ok=True)
    with lock.open('r+') as lf:
      fcntl.flock(lf, fcntl.LOCK_EX)
      existing=root/'maintenance_publication_results'/(publication_id+'.json')
      if existing.exists(): return _read_json(existing)
      if evaluation_time>=str(req.get('expiry','~')): cls='publication_expired'; return _publication_result(root,req,cls,{},evaluation_time,repository_root)
      attempts=len(list((root/'maintenance_publication_attempts').glob(publication_id+'-*.json'))) if (root/'maintenance_publication_attempts').exists() else 0
      if attempts>=int(req.get('attempt_ceiling',1)): return _publication_result(root,req,'publication_attempt_limit_reached',{},evaluation_time,repository_root)
      ordinal=attempts+1; start={'publication_id':publication_id,'attempt_ordinal':ordinal,'request_digest':req['publication_request_digest'],'commit_sha':req['commit_sha']}
      sr=journal.append_event(root,'publication_started',task_id=req['task_id'],payload=start,event_id=_id('mevent',start),repository_sha=req['commit_sha'],recorded_at=evaluation_time,repo_root=repository_root)
      if sr.status not in {'event_appended','event_already_recorded'}: return _publication_result(root,req,'publication_integrity_failed',{'journal':sr.reason_code},evaluation_time,repository_root)
      obs: dict[str, Any]={}; cls='publication_succeeded'; git=pol['git_executable']
      if req['publication_mode']=='fast_forward_base_ref':
        before=_git(git, repository_root, ['ls-remote',req['remote_name'],req['base_ref']]); oid=before.stdout.decode().split()[0] if before.stdout.strip() else ''
        obs['remote_base_before']=oid
        if oid!=req['parent_sha']: cls='publication_remote_conflict'
        else:
          push=_git(git, repository_root, ['push',req['remote_name'],f"{req['commit_sha']}:{req['base_ref']}"] ); obs['push_argv']=['push',req['remote_name'],f"{req['commit_sha']}:{req['base_ref']}"]; obs['push_returncode']=push.returncode
          after=_git(git, repository_root, ['ls-remote',req['remote_name'],req['base_ref']]); obs['remote_oid']=after.stdout.decode().split()[0] if after.stdout.strip() else ''
          if push.returncode!=0 or obs['remote_oid']!=req['commit_sha']: cls='publication_remote_unavailable'
      elif req['publication_mode']=='pull_request':
        ref='refs/heads/'+req['head_ref'].removeprefix('refs/heads/')
        before=_git(git, repository_root, ['ls-remote',req['remote_name'],ref]); oid=before.stdout.decode().split()[0] if before.stdout.strip() else ''
        if oid and oid!=req['commit_sha']: cls='publication_remote_conflict'
        elif not oid:
          push=_git(git, repository_root, ['push',req['remote_name'],f"{req['commit_sha']}:{ref}"]); obs['push_returncode']=push.returncode; obs['push_argv']=['push',req['remote_name'],f"{req['commit_sha']}:{ref}"]
          if push.returncode!=0: cls='publication_remote_unavailable'
        if cls=='publication_succeeded': cls, pr = _publish_pr(pol, req, root); obs['pr']=pr
      else: cls='publication_integrity_failed'
      return _publication_result(root,req,cls,obs,evaluation_time,repository_root,ordinal)

def _publish_pr(pol: Mapping[str,Any], req: Mapping[str,Any], root: Path)->tuple[str,dict[str,Any]]:
    exe=pol.get('publication_client_executable')
    if not exe: return 'publication_client_incompatible',{}
    env={k:v for k,v in os.environ.items() if k in pol['environment_name_allowlist']}
    body=root/'maintenance_publication_bodies'/(req['publication_id']+'.md')
    common=['--repo',req['repository_identity'],'--head',req['head_ref'],'--base',req['base_ref'].removeprefix('refs/heads/')]
    ls=_run([exe,'pr-list',*common],cwd=root,env=env,timeout=int(pol['publication_timeout_seconds']))
    if ls.returncode==3: return 'publication_authentication_unavailable',{}
    try: arr=json.loads(ls.stdout.decode() or '[]')
    except Exception: return 'publication_client_incompatible',{}
    if arr:
        pr=arr[0]
        if pr.get('headRefName')!=req['head_ref'] or pr.get('headRefOid')!=req['commit_sha'] or pr.get('baseRefName')!=req['base_ref'].removeprefix('refs/heads/') or pr.get('title')!=req['title'] or pr.get('bodyDigest')!=req['body_digest']: return 'publication_remote_conflict',pr
        return 'publication_succeeded',pr
    cr=_run([exe,'pr-create',*common,'--title',req['title'],'--body-file',str(body)],cwd=root,env=env,timeout=int(pol['publication_timeout_seconds']))
    if cr.returncode==3: return 'publication_authentication_unavailable',{}
    if cr.returncode!=0: return 'publication_retryable_failure',{'stderr_tail':cr.stderr.decode(errors='replace')[-512:]}
    return 'publication_succeeded',json.loads(cr.stdout.decode())

def _publication_result(root: Path, req: Mapping[str,Any], cls: str, obs: Mapping[str,Any], at: str, repo_root: str|Path, ordinal:int|None=None)->dict[str,Any]:
    res={'schema_version':PUBLICATION_RESULT_SCHEMA,'publication_id':req['publication_id'],'task_id':req['task_id'],'attempt_ordinal':ordinal,'request_digest':req['publication_request_digest'],'commit_sha':req['commit_sha'],'mode':req['publication_mode'],'remote_observations':dict(obs),'terminal_classification':cls,'terminal_status':cls,'recorded_at':at,'hosted_checks_waited':False,'force_push_used':False,'merge_performed':False,'credential_bytes_inspected':False,'operator_message_relayed':False}
    res['publication_result_digest']=_seal({**res,'publication_result_digest':''},'publication_result_digest')
    if cls=='publication_succeeded': _write_immutable(root/'maintenance_publication_results'/(req['publication_id']+'.json'), res)
    else: _write_immutable(root/'maintenance_publication_attempts'/(req['publication_id']+'-'+str(ordinal or 0)+'.json'), res)
    ev='publication_succeeded' if cls=='publication_succeeded' else 'publication_failed'
    journal.append_event(root,ev,task_id=req['task_id'],payload={'publication_id':req['publication_id'],'attempt_ordinal':ordinal,'publication_result_digest':res['publication_result_digest'],'terminal_classification':cls},event_id=_id('mevent',{'publication_id':req['publication_id'],'attempt_ordinal':ordinal,'terminal_classification':cls}),repository_sha=req['commit_sha'],recorded_at=at,repo_root=repo_root)
    return res
