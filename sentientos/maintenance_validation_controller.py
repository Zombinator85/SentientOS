"""Lease-bound maintenance validation controller.

Deterministic, argv-only validation and bounded same-thread corrective
continuation for detached maintenance worktrees.  The controller records evidence
under caller-supplied external state roots and never commits or publishes.
"""
from __future__ import annotations

import argparse, base64, fcntl, fnmatch, hashlib, json, math, os, shutil, signal, subprocess, sys, time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence, Callable, cast

from sentientos import maintenance_task_journal as journal
from sentientos import maintenance_local_codex_foreman as foreman
from sentientos import maintenance_task_authority_lease as authority_lease

POLICY_SCHEMA="sentientos.maintenance_validation_policy:v1"
PLAN_SCHEMA="sentientos.maintenance_validation_plan:v2"
COMMAND_RESULT_SCHEMA="sentientos.maintenance_validation_command_result:v2"
RESULT_SCHEMA="sentientos.maintenance_validation_result:v2"
CYCLE_SCHEMA="sentientos.maintenance_validation_cycle:v2"
CONTEXT_SCHEMA="sentientos.maintenance_validation_context:v1"
START_SCHEMA="sentientos.maintenance_validation_stage_start:v1"
CORRECTION_SCHEMA="sentientos.maintenance_corrective_continuation:v1"
TERMINAL_STATUSES={"validation_ready_for_commit","validation_failed_correctable","validation_failed_terminal","validation_blocked","validation_budget_exhausted","validation_timed_out","validation_interrupted","validation_workspace_changed_during_proof","corrective_continuation_started","corrective_continuation_completed","corrective_continuation_blocked","corrective_retry_limit_reached","corrective_attempt_limit_reached","corrective_lease_expired","controller_recovery_required","controller_integrity_failed"}
EXPECTATION_KINDS={"pytest_node","mypy_path","mypy_baseline","git_diff_check","docs_check_deps","docs_build","prompt_boundaries","strict_audits","audit_immutability"}
CORRECTIVE_GUARD="Continue the same bounded task in the existing worktree. Correct only the listed validation failures. Preserve the original authority, paths, base SHA, and task objective. Do not commit, push, publish, widen scope, access credentials, or wait for hosted checks."

def cj(v:Any)->bytes: return journal.canonical_json_bytes(v)
def dig(v:Any)->str: return journal.sha256_digest(v)
def seal(d:Mapping[str,Any], field:str)->str: return dig({k:v for k,v in d.items() if k!=field})
def sha_bytes(b:bytes)->str: return "sha256:"+hashlib.sha256(b).hexdigest()
def _safe_file(p:Path)->None:
    for part in (p, *p.parents):
        if part.is_symlink(): raise ValueError('custody_symlink_rejected')
    if p.exists() and not p.is_file(): raise ValueError('custody_not_regular')

def read_json(p:Path)->dict[str,Any]:
    _safe_file(p)
    def pairs(items:Any)->dict[str,Any]:
        result:dict[str,Any]={}
        for key,value in items:
            if key in result: raise ValueError('duplicate_json_key')
            result[key]=value
        return result
    value=json.loads(p.read_bytes(), object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))
    if not isinstance(value,dict): raise ValueError('invalid_json_object')
    return value
def _safe_rel(path:str)->str:
    if not path or path.startswith('/') or '\x00' in path or any(part=='..' for part in Path(path).parts): raise ValueError('unsafe_path')
    return path

def _write_immutable(path:Path, value:Mapping[str,Any])->str:
    _safe_file(path)
    path.parent.mkdir(parents=True, exist_ok=True); data=cj(value)+b"\n"
    if path.exists():
        if path.read_bytes()==data: return dig(value)
        raise ValueError('immutable_artifact_conflict')
    fd=os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0), 0o600)
    with os.fdopen(fd,'wb') as f:
        if f.write(data)!=len(data): raise OSError('short_immutable_write')
        f.flush(); os.fsync(f.fileno())
    dfd=os.open(path.parent, os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)
    if path.read_bytes()!=data: raise OSError('immutable_write_readback_mismatch')
    return dig(value)

@dataclass(frozen=True)
class ValidationPolicy:
    policy_id:str; repository_identity:str; python_executable:str=sys.executable; git_executable:str='git'; aggregate_validation_ceiling_seconds:float=120.0; per_command_default_ceiling_seconds:float=10.0; terminal_reserve_seconds:float=1.0; heartbeat_interval_seconds:float=0.1; output_tail_limit:int=4000; output_byte_limit:int=200000; external_scratch_root:str='/tmp/sentientos_validation_scratch'; maximum_controller_cycles:int=2; maximum_corrective_retries:int=1; require_declared_behavioral_test:bool=False
    @classmethod
    def from_mapping(cls,m:Mapping[str,Any])->'ValidationPolicy':
        allowed=set(cls.__dataclass_fields__)|{'schema_version','policy_digest','allowed_expectation_kinds','argv_templates','path_trigger_rules','environment_name_allowlist','correctable_failure_classifications','non_correctable_classifications','constraints'}
        if set(m)-allowed or m.get('schema_version')!=POLICY_SCHEMA: raise ValueError('invalid_policy')
        kw={k:m[k] for k in cls.__dataclass_fields__ if k in m}; obj=cls(**kw); d=obj.to_dict()
        if m.get('policy_digest') and m['policy_digest']!=d['policy_digest']: raise ValueError('invalid_policy_digest')
        return obj
    def to_dict(self)->dict[str,Any]:
        d={"schema_version":POLICY_SCHEMA, **self.__dict__, "allowed_expectation_kinds":sorted(EXPECTATION_KINDS), "argv_templates":{"pytest_node":[self.python_executable,"-m","pytest","-q","-p","no:cacheprovider","{node}"],"mypy_path":[self.python_executable,"-m","mypy","{paths}"],"mypy_baseline":[self.python_executable,"scripts/check_mypy_baseline.py"],"git_diff_check":[self.git_executable,"diff","--check"],"docs_check_deps":[self.python_executable,"scripts/build_docs.py","--check-deps"],"docs_build":[self.python_executable,"scripts/build_docs.py"],"prompt_boundaries":[self.python_executable,"scripts/verify_context_hygiene_prompt_boundaries.py"],"strict_audits":[self.python_executable,"verify_audits.py","--strict"],"audit_immutability":[self.python_executable,"scripts/audit_immutability_verifier.py"]},"path_trigger_rules":{"python":["*.py"],"docs":["docs/**","mkdocs.yml","scripts/build_docs.py"],"governance":["docs/GOVERNANCE_DOCTRINE.md","docs/AGENTS_DOCTRINE_ARCHIVE.md","sentientos/maintenance*","scripts/maintenance*","sentientos/capability_registry.py"]},"environment_name_allowlist":["PATH","HOME","LANG","LC_ALL","PYTHONDONTWRITEBYTECODE","PYTHONPYCACHEPREFIX","MYPY_CACHE_DIR","TMPDIR"],"correctable_failure_classifications":["pytest_failure","mypy_failure","diff_check_failure","docs_failure","audit_failure","prompt_boundary_failure"],"non_correctable_classifications":["invalid_plan","invalid_lease","lease_expired","worktree_identity_mismatch","source_drift","missing_validator_executable","supervisor_failure","validation_timeout","budget_exhausted","out_of_scope_failure","journal_corruption","unknown_failure_classification","missing_codex_thread_id","attempt_or_retry_ceiling"],"constraints":["argv_only","shell_false","no_commit","no_publication"],"policy_digest":""}
        d['policy_digest']=seal(d,'policy_digest'); return d

def validate_expectation(exp:str, changed:Sequence[str], admitted:Sequence[str])->tuple[str,str|None]:
    if any(x in exp for x in ['|','>','<','$(', '`']) or '=' in exp.split(':',1)[0]: raise ValueError('unsafe_expectation')
    if ':' in exp: kind,arg=exp.split(':',1)
    else: kind,arg=exp,None
    if kind not in EXPECTATION_KINDS: raise ValueError('unknown_validation_kind')
    if kind=='pytest_node':
        if not arg: raise ValueError('empty_pytest_node')
        root=arg.split('::',1)[0]; _safe_rel(root)
        if not (root.startswith('tests/') or root.endswith('.py')): raise ValueError('pytest_node_outside_repository')
    if kind=='mypy_path':
        if not arg: raise ValueError('empty_mypy_path')
        _safe_rel(arg)
        if arg not in changed and not any(arg==a.rstrip('/') or arg.startswith(a.rstrip('/')+'/') for a in admitted): raise ValueError('mypy_path_outside_admitted_or_changed')
    return kind,arg

def _argv(policy:ValidationPolicy, kind:str, arg:str|None, mypy_paths:Sequence[str]=())->list[str]:
    if kind=='pytest_node': return [policy.python_executable,'-m','pytest','-q','-p','no:cacheprovider',str(arg)]
    if kind=='mypy_path': return [policy.python_executable,'-m','mypy',*(mypy_paths or [str(arg)])]
    mp={'mypy_baseline':[policy.python_executable,'scripts/check_mypy_baseline.py'],'git_diff_check':[policy.git_executable,'diff','--check'],'docs_check_deps':[policy.python_executable,'scripts/build_docs.py','--check-deps'],'docs_build':[policy.python_executable,'scripts/build_docs.py'],'prompt_boundaries':[policy.python_executable,'scripts/verify_context_hygiene_prompt_boundaries.py'],'strict_audits':[policy.python_executable,'verify_audits.py','--strict'],'audit_immutability':[policy.python_executable,'scripts/audit_immutability_verifier.py']}
    return mp[kind]

def sanitized_environment(policy:ValidationPolicy)->tuple[dict[str,str],dict[str,Any]]:
    scratch=Path(policy.external_scratch_root); scratch.mkdir(parents=True, exist_ok=True)
    env={'PATH':os.environ.get('PATH',''),'HOME':os.environ.get('HOME',str(scratch)),'PYTHONDONTWRITEBYTECODE':'1','PYTHONPYCACHEPREFIX':str(scratch/'pycache'),'MYPY_CACHE_DIR':str(scratch/'mypy'),'TMPDIR':str(scratch),'LANG':os.environ.get('LANG','C.UTF-8')}
    names=sorted(env); return env, {'environment_names':names,'environment_name_set_digest':dig(names)}

def build_validation_plan(*, policy:ValidationPolicy, lease:Mapping[str,Any], implementation_result:Mapping[str,Any], worktree:Mapping[str,Any], change_manifest:Mapping[str,Any], remaining_validation_seconds:float|None=None, cycle_ordinal:int=1)->dict[str,Any]:
    if implementation_result.get('status')!='implementation_ready_for_validation': raise ValueError('implementation_result_not_ready')
    changed=sorted(str(p) for p in change_manifest.get('changed_paths', implementation_result.get('changed_paths',())))
    admitted=[str(p) for p in lease.get('admitted_subject_paths', changed)]
    stages: list[dict[str, Any]]=[]; seen: set[tuple[str,str|None,tuple[str,...]]]=set()
    def add(kind:str, reason:str, arg:str|None=None, paths:Sequence[str]=())->None:
        key=(kind,arg,tuple(paths))
        if key in seen: return
        seen.add(key); sid='stage_'+hashlib.sha256(cj(key)).hexdigest()[:16]
        stages.append({'stage_id':sid,'kind':kind,'argument':arg,'argv':_argv(policy,kind,arg,paths),'trigger_reasons':[reason],'timeout_seconds':policy.per_command_default_ceiling_seconds,'required':True,'argv_digest':dig(_argv(policy,kind,arg,paths))})
    add('git_diff_check','always')
    expectations=[]
    for exp in lease.get('validation_expectations',()):
        k,a=validate_expectation(str(exp),changed,admitted); expectations.append(str(exp)); add(k,'lease_expectation',a)
    py=[p for p in changed if p.endswith('.py') and not p.startswith('tests/')]
    if py:
        if policy.require_declared_behavioral_test and not any(e.startswith('pytest_node:') for e in expectations): raise ValueError('behavioral_test_required')
        add('mypy_path','python_path_trigger',paths=py); add('mypy_baseline','python_path_trigger')
    if any(p.startswith('docs/') or p in {'mkdocs.yml','scripts/build_docs.py'} for p in changed): add('docs_check_deps','docs_path_trigger'); add('docs_build','docs_path_trigger')
    if any(('maintenance' in p or 'capability' in p or 'GOVERNANCE' in p or 'AGENTS_DOCTRINE' in p or 'security' in p or 'audit' in p) for p in changed): add('prompt_boundaries','governance_path_trigger'); add('strict_audits','governance_path_trigger'); add('audit_immutability','governance_path_trigger')
    budget=sum(float(stage['timeout_seconds']) for stage in stages)+policy.terminal_reserve_seconds
    ceiling=min(float(lease.get('maximum_validation_seconds', policy.aggregate_validation_ceiling_seconds)), policy.aggregate_validation_ceiling_seconds, float(remaining_validation_seconds if remaining_validation_seconds is not None else policy.aggregate_validation_ceiling_seconds))
    if budget>ceiling: raise ValueError('validation_budget_exceeded')
    env,envm=sanitized_environment(policy)
    core={'task_id':lease['task_id'],'lease_id':lease['lease_id'],'lease_digest':lease['lease_digest'],'admitted_scope_digest':lease.get('admitted_scope_digest'),'attempt_id':implementation_result.get('attempt_id') or lease.get('attempt_id','attempt-1'),'attempt_ordinal':int(implementation_result.get('attempt_ordinal',1)),'corrective_retry_ordinal':int(implementation_result.get('corrective_retry_ordinal',0)),'implementation_session_id':implementation_result.get('session_id'),'codex_thread_id':implementation_result.get('codex_thread_id'),'implementation_result_digest':implementation_result.get('result_digest'),'worktree_descriptor_digest':worktree.get('worktree_digest'),'invocation_digest':implementation_result.get('invocation_digest'),'change_manifest_digest':change_manifest.get('manifest_digest'),'patch_digest':implementation_result.get('patch_digest'),'terminal_worktree_head':change_manifest.get('terminal_head'),'changed_paths':changed,'lease_validation_expectations':expectations,'expanded_validation_stages':stages,'aggregate_budget_seconds':budget,'remaining_lease_budget_seconds':ceiling-budget,'environment_name_set_digest':envm['environment_name_set_digest'],'policy_digest':policy.to_dict()['policy_digest'],'exhaustive_matrix_status':'not_requested_for_proportionate_validation','matrix_invocation_count':0,'validation_cycle_ordinal':cycle_ordinal,'plan_digest':''}
    core['validation_ref_id']=journal.derive_validation_ref_id(core['task_id'], core['attempt_id'], dig({'plan':core,'cycle':cycle_ordinal}))
    core['schema_version']=PLAN_SCHEMA; core['plan_digest']=seal(core,'plan_digest')
    core['canonical_inputs']={'lease':dict(lease),'implementation_result':dict(implementation_result),
        'worktree':dict(worktree),'change_manifest':dict(change_manifest),
        'remaining_validation_seconds':remaining_validation_seconds}
    core['plan_digest']=seal(core,'plan_digest')
    return core

def worktree_manifest(git:str, root:Path)->dict[str,Any]:
    head=subprocess.run([git,'rev-parse','HEAD'],cwd=root,text=True,capture_output=True,shell=False).stdout.strip()
    branch=subprocess.run([git,'branch','--show-current'],cwd=root,text=True,capture_output=True,shell=False).stdout.strip()
    status=subprocess.run([git,'status','--porcelain=v1','--untracked-files=all'],cwd=root,text=True,capture_output=True,shell=False).stdout.splitlines()
    paths=sorted((l[3:] if len(l)>3 else l) for l in status)
    contents=[]
    for p in paths:
        fp=root/p
        if fp.exists() and fp.is_file() and not fp.is_symlink(): contents.append([p,sha_bytes(fp.read_bytes())])
    return {'head':head,'branch':branch,'paths':paths,'contents':contents,'manifest_digest':dig({'head':head,'branch':branch,'paths':paths,'contents':contents})}

def _safe_pgid(pid:int)->int|None:
    try: return os.getpgid(pid)
    except ProcessLookupError: return None

def classify(kind:str, rc:int|None, stderr:str, changed:Sequence[str])->tuple[str,bool]:
    if rc==0: return ('passed',False)
    if kind=='pytest_node': return ('pytest_failure',True)
    if kind=='mypy_path': return ('mypy_failure', any(p in stderr for p in changed) or bool(changed))
    if kind=='git_diff_check': return ('diff_check_failure',True)
    if kind in {'docs_check_deps','docs_build'}: return ('docs_failure',True)
    if kind=='prompt_boundaries': return ('prompt_boundary_failure',True)
    if kind in {'strict_audits','audit_immutability'}: return ('audit_failure',True)
    return ('unknown_failure_classification',False)

def _checked(value:Mapping[str,Any], schema:str, field:str)->dict[str,Any]:
    if value.get('schema_version')!=schema or value.get(field)!=seal(value,field):
        raise ValueError('evidence_schema_or_digest_invalid')
    return dict(value)

def _component(value:Any)->str:
    if not isinstance(value,str) or not value or Path(value).name!=value or value in {'.','..'}:
        raise ValueError('invalid_custody_identity')
    return value

def _number(value:Any)->float:
    if type(value) not in (int,float) or not math.isfinite(value) or value<0:
        raise ValueError('invalid_budget_or_duration')
    return float(value)

def _git_read(git:str, root:Path, *argv:str)->bytes:
    cp=subprocess.run([git,*argv],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=False)
    if cp.returncode: raise ValueError('repository_identity_unverifiable')
    return cp.stdout

def _source(policy:ValidationPolicy, root:Path)->dict[str,Any]:
    if root.is_symlink(): raise ValueError('workspace_symlink_rejected')
    paths=sorted(set(_git_read(policy.git_executable,root,'ls-files','-z','--cached','--others','--exclude-standard').decode().split('\0'))-{''})
    files=[]
    for rel in paths:
        _safe_rel(rel); p=root/rel
        _safe_file(p)
        files.append({'path':rel,'exists':p.exists(),'mode':oct(p.stat().st_mode & 0o777) if p.exists() else None,
            'digest':sha_bytes(p.read_bytes()) if p.exists() else 'missing'})
    return {'root':str(root.resolve(strict=True)),
        'root_identity':{'device':root.stat().st_dev,'inode':root.stat().st_ino},
        'head':_git_read(policy.git_executable,root,'rev-parse','HEAD').decode().strip(),
        'branch':_git_read(policy.git_executable,root,'branch','--show-current').decode().strip(),
        'git_common_dir':str((root/_git_read(policy.git_executable,root,'rev-parse','--git-common-dir').decode().strip()).resolve()),
        'files':files}

def _execution_environment(policy:ValidationPolicy, plan:Mapping[str,Any])->tuple[dict[str,str],dict[str,Any]]:
    env,metadata=sanitized_environment(policy)
    executables={}
    for name in [policy.git_executable,*[s['argv'][0] for s in plan['expanded_validation_stages']]]:
        found=shutil.which(name,path=env['PATH'])
        if not found: raise ValueError('missing_validator_executable')
        resolved=Path(found).resolve(strict=True)
        if not resolved.is_file(): raise ValueError('invalid_validator_executable')
        executables[name]={'resolved_path':str(resolved),'content_digest':sha_bytes(resolved.read_bytes()),
            'device':resolved.stat().st_dev,'inode':resolved.stat().st_ino,
            'mode':oct(resolved.stat().st_mode & 0o777)}
    return env,{**metadata,'environment_digest':dig(env),'executables':executables,
        'measurement_boundary':'sanitized environment values and executable file bytes; not packages, interpreters of scripts, or universal host attestation'}

def _owned_input(root:Path, directories:Sequence[str], expected:Mapping[str,Any], key:str)->dict[str,Any]:
    matches=[]
    for name in directories:
        folder=root/name
        if folder.is_symlink(): raise ValueError('custody_symlink_rejected')
        for p in sorted(folder.glob('*.json')):
            obj=read_json(p)
            if obj.get(key)==expected.get(key):
                if not obj.get('schema_version') or obj.get(key)!=seal(obj,key): raise ValueError('canonical_input_bad_seal')
                matches.append(obj)
    if len(matches)!=1: raise ValueError('canonical_input_missing_or_ambiguous')
    return matches[0]

def _snapshot(root:Path, repo:Path, plan:Mapping[str,Any], at:str)->dict[str,Any]:
    path=journal.journal_path_for(root,_component(plan['task_id']),repo_root=repo)
    _safe_file(path)
    snap=journal.materialize_snapshot(root,plan['task_id'],repo_root=repo,evaluation_time=at)
    if snap.get('journal_integrity_status')!='journal_ready': raise ValueError('journal_corruption')
    if snap.get('active_lease_id')!=plan['lease_id'] or snap.get('active_lease_digest')!=plan['lease_digest'] or snap.get('lease_status')!='active':
        raise ValueError('lease_inactive_or_mismatched')
    completed=snap.get('completed_attempts',[])
    if not completed or completed[-1]['attempt_id']!=plan['attempt_id'] or completed[-1]['status']!='completed':
        raise ValueError('implementation_attempt_mismatch')
    return snap

def _plan_inputs(policy:ValidationPolicy, plan:Mapping[str,Any])->dict[str,Any]:
    _checked(plan,PLAN_SCHEMA,'plan_digest')
    _component(plan['validation_ref_id']); _component(plan['task_id'])
    inputs=plan['canonical_inputs']; lease=inputs['lease']; impl=inputs['implementation_result']; wt=inputs['worktree']; cm=inputs['change_manifest']
    expected=build_validation_plan(policy=policy,lease=lease,implementation_result=impl,
        worktree=wt,change_manifest=cm,remaining_validation_seconds=inputs['remaining_validation_seconds'],
        cycle_ordinal=plan['validation_cycle_ordinal'])
    if cj(expected)!=cj(plan): raise ValueError('plan_policy_or_input_mismatch')
    for value in [plan['aggregate_budget_seconds'],plan['remaining_lease_budget_seconds'],policy.aggregate_validation_ceiling_seconds,policy.terminal_reserve_seconds,*[s['timeout_seconds'] for s in plan['expanded_validation_stages']]]: _number(value)
    return cast(dict[str,Any],inputs)

def _verify_plan(root:Path, repo:Path, policy:ValidationPolicy, plan:Mapping[str,Any], at:str)->dict[str,Any]:
    inputs=_plan_inputs(policy,plan)
    lease=inputs['lease']; impl=inputs['implementation_result']; wt=inputs['worktree']; cm=inputs['change_manifest']
    actual_lease=authority_lease.load_lease(root,_component(lease['lease_id']),repo_root=repo)
    if cj(actual_lease)!=cj(lease) or at>=str(lease['expires_at']): raise ValueError('lease_mismatch_or_expired')
    actual_wt=_owned_input(root,['maintenance_worktrees'],wt,'worktree_digest')
    actual_cm=_owned_input(root,['maintenance_change_manifests'],cm,'manifest_digest')
    actual_impl=_owned_input(root,['maintenance_codex_results','maintenance_local_codex_results','maintenance_commissioned_local_results'],impl,'result_digest')
    for name,actual,supplied in [('worktree',actual_wt,wt),('change_manifest',actual_cm,cm),('implementation',actual_impl,impl)]:
        if any(supplied.get(k)!=v for k,v in actual.items()): raise ValueError('canonical_'+name+'_mismatch')
    for obj in [actual_wt,actual_cm,actual_impl]:
        if obj.get('task_id')!=lease['task_id'] or obj.get('session_id')!=plan['implementation_session_id']: raise ValueError('task_session_binding_mismatch')
    if actual_wt.get('lease_digest')!=lease['lease_digest'] or actual_wt.get('base_sha')!=lease['base_sha'] or actual_wt.get('repository_identity')!=policy.repository_identity or Path(actual_wt['source_repository_root']).resolve()!=repo.resolve():
        raise ValueError('worktree_repository_lease_binding_mismatch')
    for key,value in [('worktree_descriptor_digest',wt['worktree_digest']),('change_manifest_digest',cm['manifest_digest'])]:
        if actual_impl.get(key)!=value: raise ValueError('implementation_binding_mismatch')
    if actual_cm['terminal_head']!=lease['base_sha'] or actual_cm.get('out_of_scope_paths') or actual_cm.get('forbidden_paths') or actual_cm.get('budget_findings'): raise ValueError('manifest_scope_or_base_invalid')
    if sorted(actual_impl['changed_paths'])!=plan['changed_paths'] or sorted(actual_cm['changed_paths'])!=plan['changed_paths']: raise ValueError('change_set_binding_mismatch')
    for rel in plan['changed_paths']:
        _safe_rel(rel)
        if not any(rel==p.rstrip('/') or rel.startswith(p.rstrip('/')+'/') for p in lease['admitted_subject_paths']) or any(fnmatch.fnmatch(rel,p) for p in lease['forbidden_path_patterns']): raise ValueError('path_outside_lease')
    ordinal=plan['validation_cycle_ordinal']
    if type(ordinal) is not int or not 1<=ordinal<=policy.maximum_controller_cycles or ordinal>int(lease['maximum_corrective_retries'])+1: raise ValueError('cycle_ceiling')
    if plan['attempt_ordinal']>int(lease['maximum_attempts']) or plan['corrective_retry_ordinal']>min(policy.maximum_corrective_retries,int(lease['maximum_corrective_retries'])): raise ValueError('attempt_or_retry_ceiling')
    return inputs

def _match_manifest(policy:ValidationPolicy, root:Path, plan:Mapping[str,Any], source:Mapping[str,Any])->None:
    changed=set(_git_read(policy.git_executable,root,'diff','--no-renames','--name-only','-z','HEAD','--').decode().split('\0'))
    changed.update(_git_read(policy.git_executable,root,'ls-files','--others','--exclude-standard','-z').decode().split('\0'))
    changed.discard('')
    if sorted(changed)!=plan['changed_paths']: raise ValueError('measured_changed_paths_mismatch')
    manifest=plan['canonical_inputs']['change_manifest']; entries={e['path']:e for e in manifest['entries']}
    if sorted(entries)!=sorted(changed) or len(entries)!=len(manifest['entries']): raise ValueError('change_manifest_entry_coverage')
    for file in source['files']:
        if file['path'] in changed:
            entry=entries[file['path']]
            if file['exists'] and entry['content_digest']!=file['digest']: raise ValueError('change_manifest_content_mismatch')
            if not file['exists'] and entry['file_type']!='missing': raise ValueError('change_manifest_deletion_mismatch')

def _event(root:Path, repo:Path, plan:Mapping[str,Any], kind:str, payload:Mapping[str,Any], at:str, *, append:bool=True)->str:
    _snapshot(root,repo,plan,at)
    replay=journal.replay_journal(journal.journal_path_for(root,plan['task_id'],repo_root=repo))
    matches=[e for e in replay.events if e.event_type==kind and e.payload.get('validation_ref_id')==plan['validation_ref_id']]
    if matches:
        if len(matches)!=1 or cj(matches[0].payload)!=cj(payload): raise ValueError('journal_event_conflict')
        return matches[0].event_id
    if not append: raise ValueError('journal_event_missing')
    ar=journal.append_event(root,kind,task_id=plan['task_id'],payload=payload,
        event_id='mevent_'+hashlib.sha256(cj({'kind':kind,'payload':payload})).hexdigest()[:32],repo_root=repo,recorded_at=at)
    if ar.status not in {'event_appended','event_already_recorded'} or ar.event is None: raise ValueError('journal_append_failed:'+str(ar.reason_code))
    return ar.event.event_id

def _start_payload(plan:Mapping[str,Any])->dict[str,Any]:
    return {'validation_ref_id':plan['validation_ref_id'],'attempt_id':plan['attempt_id'],
        'session_id':plan['implementation_session_id'],'plan_digest':plan['plan_digest'],
        'change_manifest_digest':plan['change_manifest_digest'],'worktree_descriptor_digest':plan['worktree_descriptor_digest']}

def _command_facts(command:Mapping[str,Any], stage:Mapping[str,Any], plan:Mapping[str,Any], context:Mapping[str,Any], start:Mapping[str,Any])->tuple[str,bool]:
    _checked(command,COMMAND_RESULT_SCHEMA,'result_digest'); _checked(start,START_SCHEMA,'start_digest')
    bindings={'stage_id':stage['stage_id'],'validation_ref_id':plan['validation_ref_id'],
        'plan_digest':plan['plan_digest'],'context_digest':context['context_digest'],
        'argv':stage['argv'],'argv_digest':stage['argv_digest'],'kind':stage['kind'],'timeout_seconds':stage['timeout_seconds']}
    if any(command.get(k)!=v or start.get(k)!=v for k,v in bindings.items()) or command.get('start_digest')!=start['start_digest']:
        raise ValueError('command_binding_mismatch')
    rc=command.get('exit_code'); status=command.get('supervision_status')
    if type(rc) is not int or status not in {'exited','timed_out'}: raise ValueError('command_outcome_indeterminate')
    for stream in ['stdout','stderr']:
        raw=base64.b64decode(command[stream+'_retained_base64'],validate=True)
        if command[stream+'_digest']!=sha_bytes(raw) or command[stream+'_tail']!=raw.decode('utf-8','replace')[-context['policy']['output_tail_limit']:]: raise ValueError('retained_output_mismatch')
    duration=_number(command['duration_seconds'])
    if _number(command['ended_at'])<_number(command['started_at']) or command['started_at']!=start['started_at'] or abs(command['ended_at']-command['started_at']-duration)>.000001: raise ValueError('command_timing_mismatch')
    fc,corr=('validation_timeout',False) if status=='timed_out' else classify(stage['kind'],rc,command['stderr_tail'],plan['changed_paths'])
    if command.get('failure_class')!=fc: raise ValueError('command_classification_contradiction')
    if command.get('source_before_digest')!=dig(context['source']) or type(command.get('source_drift_detected')) is not bool or command['source_drift_detected']!=(command.get('source_after_digest')!=dig(context['source'])): raise ValueError('source_proof_contradiction')
    return fc,corr

def _load_commands(root:Path, plan:Mapping[str,Any], context:Mapping[str,Any])->list[dict[str,Any]]:
    ref=plan['validation_ref_id']; folder=root/'maintenance_validation_commands'/ref
    starts=root/'maintenance_validation_starts'/ref
    expected={s['stage_id']+'.json' for s in plan['expanded_validation_stages']}
    for directory in (folder,starts):
        if directory.is_symlink(): raise ValueError('custody_symlink_rejected')
        if directory.exists() and {p.name for p in directory.iterdir()}-expected: raise ValueError('extra_stage_evidence')
    results=[]; missing=False; failed=False
    for stage in plan['expanded_validation_stages']:
        cp=folder/(stage['stage_id']+'.json'); sp=starts/(stage['stage_id']+'.json')
        if not cp.exists():
            if sp.exists(): raise ValueError('indeterminate_stage_start')
            missing=True; continue
        if missing or failed: raise ValueError('noncontiguous_or_postfailure_command')
        command=read_json(cp); start=read_json(sp)
        fc,_=_command_facts(command,stage,plan,context,start)
        failed=fc!='passed' or command['source_drift_detected']; results.append(command)
    return results

def _aggregate(plan:Mapping[str,Any], context:Mapping[str,Any], commands:Sequence[Mapping[str,Any]])->dict[str,Any]:
    if not commands: raise ValueError('command_results_missing')
    terminal='validation_ready_for_commit'; failure=None; correctable=False
    last=commands[-1]; stage=plan['expanded_validation_stages'][len(commands)-1]
    if last['source_drift_detected']: terminal='validation_workspace_changed_during_proof'; failure='source_drift'
    elif last['supervision_status']=='timed_out': terminal='validation_timed_out'; failure='validation_timeout'
    elif last['exit_code']!=0:
        failure,correctable=classify(stage['kind'],last['exit_code'],last['stderr_tail'],plan['changed_paths'])
        terminal='validation_failed_correctable' if correctable else 'validation_failed_terminal'
    elif len(commands)!=len(plan['expanded_validation_stages']): raise ValueError('required_command_missing')
    consumed=sum(_number(c['duration_seconds']) for c in commands)
    if consumed>_number(plan['aggregate_budget_seconds']): terminal='validation_budget_exhausted'; failure='budget_exhausted'; correctable=False
    paths=set(plan['changed_paths']); manifest=[f for f in context['source']['files'] if f['path'] in paths]
    aggregate={'schema_version':RESULT_SCHEMA,'task_id':plan['task_id'],'attempt_id':plan['attempt_id'],
        'session_id':plan['implementation_session_id'],'implementation_session_id':plan['implementation_session_id'],
        'codex_thread_id':plan['codex_thread_id'],'implementation_result_digest':plan['implementation_result_digest'],
        'worktree_descriptor_digest':plan['worktree_descriptor_digest'],'change_manifest_digest':plan['change_manifest_digest'],
        'patch_digest':plan['patch_digest'],'base_sha':plan['terminal_worktree_head'],'changed_paths':plan['changed_paths'],
        'worktree_manifest':manifest,'validation_ref_id':plan['validation_ref_id'],'plan_digest':plan['plan_digest'],
        'context_digest':context['context_digest'],'command_result_digests':[c['result_digest'] for c in commands],
        'required_stage_outcomes':[{'stage_id':c['stage_id'],'exit_code':c['exit_code'],'failure_class':c['failure_class']} for c in commands],
        'skipped_stages':[],'total_duration_seconds':consumed,'total_budget_consumed_seconds':consumed,
        'cumulative_task_validation_seconds':context['prior_consumed_seconds']+consumed,
        'source_drift_proof':{'before':dig(context['source']),'after':last['source_after_digest'],'source_drift_detected':last['source_drift_detected']},
        'exhaustive_matrix_status':plan['exhaustive_matrix_status'],'matrix_invocation_count':0,
        'terminal_status':terminal,'failure_classification':failure,'correctable':correctable,
        'journal_required':context['journal_required'],'journal_terminal_event_id':None,'result_digest':''}
    aggregate['result_digest']=seal(aggregate,'result_digest'); return aggregate

def _terminal_payload(plan:Mapping[str,Any], result:Mapping[str,Any])->dict[str,Any]:
    return {**_start_payload(plan),'result_digest':result['result_digest'],
        'terminal_status':result['terminal_status'],'correctable':result['correctable']}

def _prior_consumption(root:Path, repo:Path, plan:Mapping[str,Any])->float:
    """Recheck frozen failed cycles, whose implementation may since be corrected.

    Historical bytes are not recertified as current readiness. Their completed
    command evidence and original journal custody conserve consumed authority.
    """
    prior=[]
    for path in (root/'maintenance_validation_results').glob('*.json'):
        result=read_json(path)
        if result.get('task_id')!=plan['task_id'] or result.get('validation_ref_id')==plan['validation_ref_id']: continue
        ref=_component(result['validation_ref_id'])
        old_plan=read_json(root/'maintenance_validation_plans'/(ref+'.json'))
        if old_plan['validation_cycle_ordinal']>=plan['validation_cycle_ordinal']: continue
        context=_checked(read_json(root/'maintenance_validation_contexts'/(ref+'.json')),CONTEXT_SCHEMA,'context_digest')
        policy=ValidationPolicy.from_mapping(context['policy']); _plan_inputs(policy,old_plan)
        if old_plan['task_id']!=plan['task_id'] or old_plan['lease_digest']!=plan['lease_digest'] or context['repository_root']!=str(repo.resolve()) or context['plan_digest']!=old_plan['plan_digest']: raise ValueError('prior_cycle_binding_mismatch')
        cycle=_checked(read_json(root/'maintenance_validation_cycles'/(ref+'.json')),CYCLE_SCHEMA,'cycle_digest')
        if cycle['plan_digest']!=old_plan['plan_digest'] or cycle['context_digest']!=context['context_digest'] or cycle['validation_ref_id']!=ref: raise ValueError('prior_cycle_binding_mismatch')
        _checked(result,RESULT_SCHEMA,'result_digest')
        if cj(result)!=cj(_aggregate(old_plan,context,_load_commands(root,old_plan,context))): raise ValueError('prior_cycle_semantic_contradiction')
        if result['terminal_status']!='validation_failed_correctable': raise ValueError('prior_cycle_not_correctable')
        replay=journal.replay_journal(journal.journal_path_for(root,plan['task_id'],repo_root=repo))
        for kind,payload in [('validation_started',_start_payload(old_plan)),('validation_failed',_terminal_payload(old_plan,result))]:
            matches=[e for e in replay.events if e.event_type==kind and e.payload.get('validation_ref_id')==ref]
            if len(matches)!=1 or cj(matches[0].payload)!=cj(payload): raise ValueError('prior_cycle_journal_mismatch')
        prior.append((old_plan['validation_cycle_ordinal'],context,result))
    prior.sort(key=lambda entry:entry[0])
    if [entry[0] for entry in prior]!=list(range(1,plan['validation_cycle_ordinal'])): raise ValueError('prior_cycle_coverage_mismatch')
    consumed=0.0
    for _,context,result in prior:
        if _number(context['prior_consumed_seconds'])!=consumed: raise ValueError('prior_cycle_budget_mismatch')
        consumed+=_number(result['total_budget_consumed_seconds'])
    return consumed

def verify_validation_evidence(*, state_root:Path, repository_root:Path, validation_ref_id:str,
    evaluation_time:str, policy:ValidationPolicy|None=None, worktree_root:Path|None=None,
    require_ready:bool=True, require_journal:bool=True)->dict[str,Any]:
    """Load canonical custody. Integrity, command success and journal custody are distinct."""
    ref=_component(validation_ref_id); root=Path(state_root); repo=Path(repository_root)
    if (root/'maintenance_validation_errors'/ref).exists(): raise ValueError('prior_persistence_failure')
    plan=read_json(root/'maintenance_validation_plans'/(ref+'.json'))
    context=_checked(read_json(root/'maintenance_validation_contexts'/(ref+'.json')),CONTEXT_SCHEMA,'context_digest')
    stored_policy=ValidationPolicy.from_mapping(context['policy']); policy=policy or stored_policy
    if policy.to_dict()!=context['policy']: raise ValueError('current_policy_mismatch')
    _verify_plan(root,repo,policy,plan,evaluation_time)
    if context['plan_digest']!=plan['plan_digest'] or context['repository_root']!=str(repo.resolve()): raise ValueError('context_binding_mismatch')
    if _number(context['prior_consumed_seconds'])!=_prior_consumption(root,repo,plan): raise ValueError('prior_cycle_budget_mismatch')
    cycle=_checked(read_json(root/'maintenance_validation_cycles'/(ref+'.json')),CYCLE_SCHEMA,'cycle_digest')
    if cycle['plan_digest']!=plan['plan_digest'] or cycle['context_digest']!=context['context_digest'] or cycle['validation_ref_id']!=ref: raise ValueError('cycle_binding_mismatch')
    commands=_load_commands(root,plan,context)
    result=_checked(read_json(root/'maintenance_validation_results'/(ref+'.json')),RESULT_SCHEMA,'result_digest')
    if cj(result)!=cj(_aggregate(plan,context,commands)): raise ValueError('aggregate_semantic_contradiction')
    if require_ready and result['terminal_status']!='validation_ready_for_commit': raise ValueError('validation_commands_not_successful')
    ceiling=min(_number(plan['canonical_inputs']['lease']['maximum_validation_seconds']),policy.aggregate_validation_ceiling_seconds)
    if _number(result['cumulative_task_validation_seconds'])>ceiling: raise ValueError('task_budget_exhausted')
    if worktree_root is not None:
        _,env=_execution_environment(policy,plan)
        if env!=context['execution_environment']: raise ValueError('execution_environment_changed')
        if _source(policy,worktree_root)!=context['source']: raise ValueError('source_changed_since_validation')
    if require_journal:
        if context['journal_required'] is not True: raise ValueError('diagnostic_validation_not_authority')
        _event(root,repo,plan,'validation_started',_start_payload(plan),evaluation_time,append=False)
        kind='validation_passed' if result['terminal_status']=='validation_ready_for_commit' else 'validation_failed'
        _event(root,repo,plan,kind,_terminal_payload(plan,result),evaluation_time,append=False)
        snap=_snapshot(root,repo,plan,evaluation_time)
        if snap.get('validation_result',{}).get('payload',{}).get('result_digest')!=result['result_digest']: raise ValueError('not_current_validation_cycle')
    return {'plan':plan,'context':context,'commands':commands,'result':result}

def run_validation_plan(*, state_root:Path, repository_root:Path, worktree_root:Path, policy:ValidationPolicy, plan:Mapping[str,Any], evaluation_time:str, append_journal:bool=True)->dict[str,Any]:
    root=state_root; repo=repository_root; ref=_component(plan['validation_ref_id'])
    lock=root/'maintenance_validation_locks'/(_component(plan['task_id'])+'.lock'); _safe_file(lock); lock.parent.mkdir(parents=True,exist_ok=True)
    try:
      with lock.open('a') as lf:
        try: fcntl.flock(lf,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return {'status':'validation_blocked','reason_code':'controller_already_running'}
        if (root/'maintenance_validation_errors'/ref).exists(): raise ValueError('prior_persistence_failure')
        inputs=_verify_plan(root,repo,policy,plan,evaluation_time)
        _write_immutable(root/'maintenance_validation_plans'/(ref+'.json'),plan)
        env,env_proof=_execution_environment(policy,plan)
        context_path=root/'maintenance_validation_contexts'/(ref+'.json')
        if context_path.exists():
            original=_checked(read_json(context_path),CONTEXT_SCHEMA,'context_digest')
            if original['execution_environment']!=env_proof: raise ValueError('execution_environment_changed')
        source=_source(policy,worktree_root)
        _match_manifest(policy,worktree_root,plan,source)
        if source['root']!=str(Path(inputs['worktree']['worktree_root']).resolve()) or source['head']!=inputs['lease']['base_sha'] or source['branch']: raise ValueError('worktree_identity_mismatch')
        common=str((repo/_git_read(policy.git_executable,repo,'rev-parse','--git-common-dir').decode().strip()).resolve())
        if source['git_common_dir']!=common: raise ValueError('wrong_repository')
        if context_path.exists():
            context=_checked(read_json(context_path),CONTEXT_SCHEMA,'context_digest')
            if context['plan_digest']!=plan['plan_digest'] or context['policy']!=policy.to_dict() or context['source']!=source or context['execution_environment']!=env_proof or context['journal_required'] is not append_journal: raise ValueError('original_execution_context_changed')
        else:
            if any((root/d/ref).exists() for d in ['maintenance_validation_commands','maintenance_validation_starts']) or (root/'maintenance_validation_results'/(ref+'.json')).exists(): raise ValueError('original_context_missing')
            patch=sha_bytes(_git_read(policy.git_executable,worktree_root,'diff','--binary','HEAD','--'))
            if patch!=plan['patch_digest']: raise ValueError('patch_digest_mismatch')
            prior=_prior_consumption(root,repo,plan)
            context={'schema_version':CONTEXT_SCHEMA,'plan_digest':plan['plan_digest'],'repository_root':str(repo.resolve()),
                'source':source,'execution_environment':env_proof,'policy':policy.to_dict(),'journal_required':append_journal,
                'prior_consumed_seconds':prior,'created_at':time.time(),'context_digest':''}
            context['context_digest']=seal(context,'context_digest'); _write_immutable(context_path,context)
        cycle={'schema_version':CYCLE_SCHEMA,'validation_ref_id':ref,'plan_digest':plan['plan_digest'],'context_digest':context['context_digest'],'cycle_digest':''}
        cycle['cycle_digest']=seal(cycle,'cycle_digest'); _write_immutable(root/'maintenance_validation_cycles'/(ref+'.json'),cycle)
        if append_journal: _event(root,repo,plan,'validation_started',_start_payload(plan),evaluation_time)
        aggregate_path=root/'maintenance_validation_results'/(ref+'.json')
        if aggregate_path.exists():
            result=verify_validation_evidence(state_root=root,repository_root=repo,validation_ref_id=ref,
                evaluation_time=evaluation_time,policy=policy,worktree_root=worktree_root,require_ready=False,require_journal=False)['result']
        else:
            commands=_load_commands(root,plan,context)
            for stage in plan['expanded_validation_stages'][len(commands):]:
                if commands and (commands[-1]['failure_class']!='passed' or commands[-1]['source_drift_detected']): break
                elapsed=time.time()-_number(context['created_at'])
                if elapsed<0 or elapsed>=plan['aggregate_budget_seconds']: raise ValueError('original_cycle_budget_exhausted')
                consumed=sum(_number(c['duration_seconds']) for c in commands)
                if context['prior_consumed_seconds']+consumed+_number(stage['timeout_seconds'])>min(_number(inputs['lease']['maximum_validation_seconds']),policy.aggregate_validation_ceiling_seconds): raise ValueError('task_budget_exhausted')
                if _execution_environment(policy,plan)[1]!=env_proof or _source(policy,worktree_root)!=source: raise ValueError('execution_context_changed_before_launch')
                start={'schema_version':START_SCHEMA,'validation_ref_id':ref,'plan_digest':plan['plan_digest'],
                    'context_digest':context['context_digest'],'stage_id':stage['stage_id'],'kind':stage['kind'],
                    'argv':stage['argv'],'argv_digest':stage['argv_digest'],'timeout_seconds':stage['timeout_seconds'],
                    'started_at':time.time(),'start_digest':''}
                start['start_digest']=seal(start,'start_digest'); _write_immutable(root/'maintenance_validation_starts'/ref/(stage['stage_id']+'.json'),start)
                proc=subprocess.Popen(list(stage['argv']),cwd=worktree_root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=False,env=env,start_new_session=True)
                timed=False
                try: out,err=proc.communicate(timeout=min(float(stage['timeout_seconds']),max(.001,context['created_at']+plan['aggregate_budget_seconds']-time.time())))
                except subprocess.TimeoutExpired:
                    timed=True
                    try: os.killpg(proc.pid,signal.SIGTERM)
                    except ProcessLookupError: pass
                    time.sleep(.05)
                    try: os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                    out,err=proc.communicate()
                ended=time.time()
                if _execution_environment(policy,plan)[1]!=env_proof: raise ValueError('execution_environment_changed_during_command')
                after=_source(policy,worktree_root)
                fc,_=('validation_timeout',False) if timed else classify(stage['kind'],proc.returncode,err.decode('utf-8','replace'),plan['changed_paths'])
                cr={k:v for k,v in start.items() if k not in {'schema_version','start_digest'}}
                cr.update(schema_version=COMMAND_RESULT_SCHEMA,start_digest=start['start_digest'],ended_at=ended,
                    duration_seconds=ended-start['started_at'],exit_code=proc.returncode,supervision_status='timed_out' if timed else 'exited',
                    failure_class=fc,source_before_digest=dig(source),source_after_digest=dig(after),source_drift_detected=source!=after,
                    process_identity={'pid':proc.pid,'process_group_id':proc.pid})
                for name,raw in [('stdout',out),('stderr',err)]:
                    retained=raw[:policy.output_byte_limit]; cr[name+'_retained_base64']=base64.b64encode(retained).decode('ascii')
                    cr[name+'_digest']=sha_bytes(retained); cr[name+'_tail']=retained.decode('utf-8','replace')[-policy.output_tail_limit:]
                cr['result_digest']=seal(cr,'result_digest'); _command_facts(cr,stage,plan,context,start)
                _write_immutable(root/'maintenance_validation_commands'/ref/(stage['stage_id']+'.json'),cr); commands.append(cr)
            result=_aggregate(plan,context,commands)
            _write_immutable(aggregate_path,result)
        result=verify_validation_evidence(state_root=root,repository_root=repo,validation_ref_id=ref,
            evaluation_time=evaluation_time,policy=policy,require_ready=False,require_journal=False,
            worktree_root=worktree_root if result['terminal_status']=='validation_ready_for_commit' else None)['result']
        if append_journal:
            kind='validation_passed' if result['terminal_status']=='validation_ready_for_commit' else 'validation_failed'
            _event(root,repo,plan,kind,_terminal_payload(plan,result),evaluation_time)
        return cast(dict[str,Any],result)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        if isinstance(exc,OSError):
            # A possibly complete file after a failed durability operation cannot
            # certify itself on recovery. Retain a denial marker without rewriting it.
            marker=root/'maintenance_validation_errors'/ref
            try:
                marker.parent.mkdir(parents=True,exist_ok=True)
                fd=os.open(marker,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
                with os.fdopen(fd,'wb') as f: f.write(type(exc).__name__.encode()); f.flush(); os.fsync(f.fileno())
                dfd=os.open(marker.parent,os.O_RDONLY)
                try: os.fsync(dfd)
                finally: os.close(dfd)
            except OSError: pass
        return {'schema_version':RESULT_SCHEMA,'status':'controller_integrity_failed','reason_code':str(exc),'validation_ref_id':ref}


def build_correction_envelope(*, state_root:Path, plan:Mapping[str,Any], result:Mapping[str,Any], lease:Mapping[str,Any], previous_result:Mapping[str,Any])->dict[str,Any]:
    failing=[r for r in result.get('required_stage_outcomes',()) if r.get('exit_code')]
    if not result.get('correctable'): raise ValueError('noncorrectable_failure')
    new_attempt=int(plan.get('attempt_ordinal',1))+1; new_retry=int(plan.get('corrective_retry_ordinal',0))+1
    if new_retry>int(lease.get('maximum_corrective_retries',1)): raise ValueError('corrective_retry_limit_reached')
    env={'schema_version':CORRECTION_SCHEMA,'task_id':plan['task_id'],'lease_id':plan['lease_id'],'lease_digest':plan['lease_digest'],'admitted_scope_digest':plan.get('admitted_scope_digest'),'failed_validation_ref_id':plan['validation_ref_id'],'failed_validation_result_digest':result['result_digest'],'prior_implementation_attempt_id':plan['attempt_id'],'prior_implementation_session_id':plan.get('implementation_session_id'),'prior_codex_thread_id':plan.get('codex_thread_id'),'new_attempt_ordinal':new_attempt,'new_corrective_retry_ordinal':new_retry,'same_worktree_descriptor_digest':plan.get('worktree_descriptor_digest'),'same_base_sha':lease.get('base_sha'),'changed_paths':plan.get('changed_paths',()),'failing_stage_ids':[f['stage_id'] for f in failing],'exit_codes':[f.get('exit_code') for f in failing],'stable_failure_classes':[f.get('failure_class') for f in failing],'bounded_output_tails':[],'output_digests':result.get('command_result_digests',()),'immutable_scope_constraints':lease.get('admitted_subject_paths',()),'remaining_budgets':{'validation_seconds':plan.get('remaining_lease_budget_seconds')},'disclosed_correction_text':CORRECTIVE_GUARD,'continuation_digest':''}
    env['continuation_digest']=seal(env,'continuation_digest'); _write_immutable(state_root/'maintenance_corrective_continuations'/(plan['validation_ref_id']+'.json'),env); return env

def start_corrective_local_codex_session(config:foreman.LocalCodexForemanConfig, lease:Mapping[str,Any], request:Mapping[str,Any], session:Mapping[str,Any], artifact_root:Path, correction_envelope:Mapping[str,Any], evaluation_time:str)->dict[str,Any]:
    if not correction_envelope.get('prior_codex_thread_id'): return {'schema_version':foreman.RESULT_SCHEMA,'status':'foreman_recovery_unavailable','reason_codes':['missing_codex_thread_id']}
    if evaluation_time>=str(lease.get('expires_at','9999')): return {'schema_version':foreman.RESULT_SCHEMA,'status':'foreman_recovery_unavailable','reason_codes':['lease_expired']}
    return foreman.run_local_codex_session(config, lease, request, session, artifact_root, recovery_ordinal=1, resume_thread_id=str(correction_envelope['prior_codex_thread_id']))

def advance_validation_controller(*, state_root:Path, repository_root:Path,
    policy:ValidationPolicy, lease:Mapping[str,Any], implementation_result:Mapping[str,Any],
    worktree:Mapping[str,Any], change_manifest:Mapping[str,Any], request:Mapping[str,Any],
    session:Mapping[str,Any], foreman_config:foreman.LocalCodexForemanConfig,
    evaluation_time:str, recovery_plan:Mapping[str,Any]|None=None,
    corrective_continuation:Callable[[Mapping[str,Any]],Mapping[str,Any]]|None=None)->dict[str,Any]:
    """Own one bounded validation/correction operation over exact caller bindings.

    The watchdog is intentionally only an identity-binding adapter.  Planning,
    execution, same-thread correction, remeasurement and immutable validation
    custody remain here beside the controller's existing primitives.
    """
    plan=dict(recovery_plan) if recovery_plan is not None else build_validation_plan(
        policy=policy, lease=lease, implementation_result=implementation_result,
        worktree=worktree, change_manifest=change_manifest)
    result=run_validation_plan(state_root=state_root,repository_root=repository_root,
        worktree_root=Path(str(worktree['worktree_root'])),policy=policy,plan=plan,
        evaluation_time=evaluation_time)
    if result.get('terminal_status')=='validation_failed_correctable':
        if plan['attempt_ordinal']>=int(lease['maximum_attempts']):
            return {'status':'corrective_attempt_limit_reached','validation_result':result,'validation_plan':plan}
        if plan['validation_cycle_ordinal']>=policy.maximum_controller_cycles or plan['corrective_retry_ordinal']>=min(policy.maximum_corrective_retries,int(lease['maximum_corrective_retries'])):
            return {'status':'corrective_retry_limit_reached','validation_result':result,'validation_plan':plan}
        try:
            envelope=build_correction_envelope(state_root=state_root,plan=plan,result=result,
                lease=lease,previous_result=implementation_result)
        except ValueError as exc:
            return {'status':str(exc),'validation_result':result,'validation_plan':plan}
        corrected=dict(corrective_continuation(envelope)) if corrective_continuation else start_corrective_local_codex_session(
            foreman_config,lease,request,session,state_root,envelope,evaluation_time)
        if corrected.get('status')!='implementation_ready_for_validation':
            return {'status':'corrective_continuation_blocked','reason_code':corrected.get('status'),
                    'validation_result':result,'correction_result':corrected}
        corrected=dict(corrected)
        corrected.update(attempt_id=session.get('attempt_id'),
            attempt_ordinal=envelope['new_attempt_ordinal'],
            corrective_retry_ordinal=envelope['new_corrective_retry_ordinal'])
        measured=read_json(state_root/'maintenance_change_manifests'/(str(session['session_id'])+'.json'))
        if measured.get('manifest_digest')!=corrected.get('change_manifest_digest'):
            return {'status':'controller_integrity_failed','reason_code':'corrected_manifest_digest_mismatch'}
        plan=build_validation_plan(policy=policy,lease=lease,implementation_result=corrected,
            worktree=worktree,change_manifest=measured,
            remaining_validation_seconds=plan.get('remaining_lease_budget_seconds'),cycle_ordinal=2)
        result=run_validation_plan(state_root=state_root,repository_root=repository_root,
            worktree_root=Path(str(worktree['worktree_root'])),policy=policy,plan=plan,
            evaluation_time=evaluation_time)
    if result.get('terminal_status')=='validation_ready_for_commit':
        payload={'validation_ref_id':plan['validation_ref_id'],'attempt_id':plan['attempt_id'],
                 'result_digest':result['result_digest'],'plan_digest':plan['plan_digest'],
                 'worktree_descriptor_digest':plan.get('worktree_descriptor_digest'),
                 'change_manifest_digest':plan.get('change_manifest_digest')}
        try:
            verify_validation_evidence(state_root=state_root,repository_root=repository_root,
                validation_ref_id=plan['validation_ref_id'],evaluation_time=evaluation_time,
                policy=policy,worktree_root=Path(str(worktree['worktree_root'])))
            _event(state_root,repository_root,plan,'ready_to_commit_recorded',payload,evaluation_time)
        except (ValueError,OSError,KeyError,TypeError) as exc:
            return {'status':'controller_integrity_failed','reason_code':str(exc)}
    return {'status':result.get('terminal_status','controller_integrity_failed'),
            'validation_result':result,'validation_plan':plan}

def inspect(state_root:Path, task_id:str)->dict[str,Any]:
    vals=sorted((state_root/'maintenance_validation_results').glob('*.json')) if (state_root/'maintenance_validation_results').exists() else []
    envs=sorted((state_root/'maintenance_corrective_continuations').glob('*.json')) if (state_root/'maintenance_corrective_continuations').exists() else []
    return {'schema_version':RESULT_SCHEMA,'status':'inspect_ready','task_id':task_id,'validation_results':[read_json(p) for p in vals],'correction_envelopes':[read_json(p) for p in envs]}

def main(argv:Sequence[str]|None=None)->int:
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    for name in ('plan','validate','advance','recover','cancel','inspect','verify-result'):
        sp=sub.add_parser(name); sp.add_argument('--state-root',required=True); sp.add_argument('--workspace-root'); sp.add_argument('--repository-root',required=True); sp.add_argument('--task-id',required=True); sp.add_argument('--lease-id'); sp.add_argument('--foreman-result'); sp.add_argument('--validation-policy'); sp.add_argument('--worktree-descriptor'); sp.add_argument('--change-manifest'); sp.add_argument('--plan'); sp.add_argument('--evaluation-time',required=True)
    ns=ap.parse_args(argv); state=Path(ns.state_root); repo=Path(ns.repository_root)
    try:
        if ns.cmd=='inspect': print(json.dumps(inspect(state,ns.task_id),sort_keys=True)); return 0
        if ns.cmd=='verify-result':
            r=read_json(Path(ns.plan)); intact=r.get('result_digest')==seal(r,'result_digest')
            try:
                if not intact: raise ValueError('invalid_result_digest')
                proof=verify_validation_evidence(state_root=state,repository_root=repo,
                    validation_ref_id=r['validation_ref_id'],evaluation_time=ns.evaluation_time)
                if proof['plan']['task_id']!=ns.task_id: raise ValueError('cli_task_binding_mismatch')
                if cj(r)!=cj(proof['result']): raise ValueError('noncanonical_result')
                verify_validation_evidence(state_root=state,repository_root=repo,
                    validation_ref_id=r['validation_ref_id'],evaluation_time=ns.evaluation_time,
                    worktree_root=Path(proof['context']['source']['root']))
            except (ValueError,OSError,KeyError,TypeError) as exc:
                print(json.dumps({'status':'validation_not_ready','integrity_valid':intact,
                    'semantic_readiness':False,'reason_code':str(exc)},sort_keys=True)); return 2
            print(json.dumps({'status':'validation_result_verified','integrity_valid':True,'semantic_readiness':True},sort_keys=True)); return 0
        pol=ValidationPolicy.from_mapping(read_json(Path(ns.validation_policy)))
        if ns.cmd=='plan':
            lease=read_json(Path(ns.lease_id)); impl=read_json(Path(ns.foreman_result)); wt=read_json(Path(ns.worktree_descriptor)); cm=read_json(Path(ns.change_manifest)); plan=build_validation_plan(policy=pol,lease=lease,implementation_result=impl,worktree=wt,change_manifest=cm); print(json.dumps(plan,sort_keys=True)); return 0
        if ns.cmd in {'validate','advance','recover'}:
            plan=read_json(Path(ns.plan)); wt=read_json(Path(ns.worktree_descriptor)); res=run_validation_plan(state_root=state,repository_root=repo,worktree_root=Path(wt['worktree_root']),policy=pol,plan=plan,evaluation_time=ns.evaluation_time); print(json.dumps(res,sort_keys=True)); return 0 if res.get('terminal_status')=='validation_ready_for_commit' or res.get('status') in TERMINAL_STATUSES else 2
        if ns.cmd=='cancel': print(json.dumps({'status':'validation_interrupted','task_id':ns.task_id},sort_keys=True)); return 0
    except Exception as e:
        print(json.dumps({'status':'controller_integrity_failed','reason_code':str(e)},sort_keys=True)); return 2
    return 2
if __name__=='__main__': raise SystemExit(main())
