"""Lease-bound maintenance validation controller.

Deterministic, argv-only validation and bounded same-thread corrective
continuation for detached maintenance worktrees.  The controller records evidence
under caller-supplied external state roots and never commits or publishes.
"""
from __future__ import annotations

import argparse, fcntl, hashlib, json, os, signal, subprocess, sys, time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence, Callable, cast

from sentientos import maintenance_task_journal as journal
from sentientos import maintenance_local_codex_foreman as foreman

POLICY_SCHEMA="sentientos.maintenance_validation_policy:v1"
PLAN_SCHEMA="sentientos.maintenance_validation_plan:v1"
COMMAND_RESULT_SCHEMA="sentientos.maintenance_validation_command_result:v1"
RESULT_SCHEMA="sentientos.maintenance_validation_result:v1"
CYCLE_SCHEMA="sentientos.maintenance_validation_cycle:v1"
CORRECTION_SCHEMA="sentientos.maintenance_corrective_continuation:v1"
TERMINAL_STATUSES={"validation_ready_for_commit","validation_failed_correctable","validation_failed_terminal","validation_blocked","validation_budget_exhausted","validation_timed_out","validation_interrupted","validation_workspace_changed_during_proof","corrective_continuation_started","corrective_continuation_completed","corrective_continuation_blocked","corrective_retry_limit_reached","corrective_attempt_limit_reached","corrective_lease_expired","controller_recovery_required","controller_integrity_failed"}
EXPECTATION_KINDS={"pytest_node","mypy_path","mypy_baseline","git_diff_check","docs_check_deps","docs_build","prompt_boundaries","strict_audits","audit_immutability"}
CORRECTIVE_GUARD="Continue the same bounded task in the existing worktree. Correct only the listed validation failures. Preserve the original authority, paths, base SHA, and task objective. Do not commit, push, publish, widen scope, access credentials, or wait for hosted checks."

def cj(v:Any)->bytes: return journal.canonical_json_bytes(v)
def dig(v:Any)->str: return journal.sha256_digest(v)
def seal(d:Mapping[str,Any], field:str)->str: return dig({k:v for k,v in d.items() if k!=field})
def sha_bytes(b:bytes)->str: return "sha256:"+hashlib.sha256(b).hexdigest()
def read_json(p:Path)->dict[str,Any]: return cast(dict[str,Any], json.loads(p.read_text()))
def _safe_rel(path:str)->str:
    if not path or path.startswith('/') or '\x00' in path or any(part=='..' for part in Path(path).parts): raise ValueError('unsafe_path')
    return path

def _write_immutable(path:Path, value:Mapping[str,Any])->str:
    path.parent.mkdir(parents=True, exist_ok=True); data=cj(value)+b"\n"
    if path.exists():
        if path.read_bytes()==data: return dig(value)
        raise ValueError('immutable_artifact_conflict')
    fd=os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0), 0o600)
    with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
    dfd=os.open(path.parent, os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)
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

def run_validation_plan(*, state_root:Path, repository_root:Path, worktree_root:Path, policy:ValidationPolicy, plan:Mapping[str,Any], evaluation_time:str, append_journal:bool=True)->dict[str,Any]:
    lock=state_root/'maintenance_validation_locks'/(plan['task_id']+'.lock'); lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('w') as lf:
      try: fcntl.flock(lf, fcntl.LOCK_EX|fcntl.LOCK_NB)
      except BlockingIOError: return {'schema_version':RESULT_SCHEMA,'status':'validation_blocked','reason_code':'controller_already_running','validation_ref_id':plan['validation_ref_id']}
      ref=plan['validation_ref_id']
      existing_result=state_root/'maintenance_validation_results'/(ref+'.json')
      if existing_result.exists(): return read_json(existing_result)
      cycle={'schema_version':CYCLE_SCHEMA,'validation_ref_id':ref,'plan_digest':plan['plan_digest'],'cycle_digest':''}; cycle['cycle_digest']=seal(cycle,'cycle_digest'); _write_immutable(state_root/'maintenance_validation_cycles'/(ref+'.json'),cycle)
      if append_journal:
        payload={'validation_ref_id':ref,'attempt_id':plan['attempt_id'],'session_id':plan.get('implementation_session_id'),'plan_digest':plan['plan_digest'],'change_manifest_digest':plan.get('change_manifest_digest'),'worktree_descriptor_digest':plan.get('worktree_descriptor_digest')}
        ar=journal.append_event(state_root,'validation_started',task_id=plan['task_id'],payload=payload,event_id='mevent_'+hashlib.sha256(cj(payload)).hexdigest()[:32],repo_root=repository_root,recorded_at=evaluation_time)
        if ar.status not in {'event_appended','event_already_recorded'}: return {'schema_version':RESULT_SCHEMA,'status':'controller_integrity_failed','reason_code':ar.reason_code,'validation_ref_id':ref}
      env,envm=sanitized_environment(policy); before=worktree_manifest(policy.git_executable, worktree_root); results=[]; start=time.time(); terminal='validation_ready_for_commit'; failure_class=None; correctable=False
      for st in plan['expanded_validation_stages']:
        cp_path=state_root/'maintenance_validation_commands'/ref/(st['stage_id']+'.json')
        if cp_path.exists(): cr=read_json(cp_path); results.append(cr); continue
        s=time.time(); proc=subprocess.Popen(list(st['argv']),cwd=worktree_root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=False,shell=False,env=env,start_new_session=True)
        timed=False
        try: out,err=proc.communicate(timeout=float(st['timeout_seconds']))
        except subprocess.TimeoutExpired:
            timed=True; os.killpg(os.getpgid(proc.pid), signal.SIGTERM); time.sleep(0.05)
            if proc.poll() is None: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            out,err=proc.communicate(); terminal='validation_timed_out'; failure_class='validation_timeout'
        rc=proc.returncode; out=out[:policy.output_byte_limit]; err=err[:policy.output_byte_limit]
        fc,is_corr=classify(st['kind'],rc,err.decode('utf-8','replace'),plan['changed_paths']) if not timed else ('validation_timeout',False)
        cr={'schema_version':COMMAND_RESULT_SCHEMA,'stage_id':st['stage_id'],'validation_ref_id':ref,'plan_digest':plan['plan_digest'],'argv_digest':st['argv_digest'],'argv':list(st['argv']),'cwd_worktree_digest':plan.get('worktree_descriptor_digest'),'environment_name_set_digest':envm['environment_name_set_digest'],'started_at':s,'ended_at':time.time(),'duration_seconds':time.time()-s,'exit_code':rc,'supervision_status':'timed_out' if timed else 'exited','process_identity':{'pid':proc.pid,'process_group_id':_safe_pgid(proc.pid) if not timed else None},'stdout_tail':out.decode('utf-8','replace')[-policy.output_tail_limit:],'stderr_tail':err.decode('utf-8','replace')[-policy.output_tail_limit:],'stdout_digest':sha_bytes(out),'stderr_digest':sha_bytes(err),'failure_class':fc,'result_digest':''}
        cr['result_digest']=seal(cr,'result_digest'); _write_immutable(cp_path,cr); results.append(cr)
        after=worktree_manifest(policy.git_executable, worktree_root)
        if after['head']!=before['head'] or after['branch']!=before['branch'] or after['manifest_digest']!=before['manifest_digest']:
            terminal='validation_workspace_changed_during_proof'; failure_class='source_drift'; correctable=False; break
        if timed:
            correctable=False; break
        if rc!=0:
            terminal='validation_failed_correctable' if is_corr else 'validation_failed_terminal'; failure_class=fc; correctable=is_corr; break
      after=worktree_manifest(policy.git_executable, worktree_root)
      if terminal=='validation_ready_for_commit' and (after['head']!=before['head'] or after['branch']!=before['branch'] or after['manifest_digest']!=before['manifest_digest']): terminal='validation_workspace_changed_during_proof'; failure_class='source_drift'
      validated_manifest=[{'path':p,'exists':(worktree_root/p).exists(),'mode':oct((worktree_root/p).stat().st_mode & 0o777) if (worktree_root/p).exists() else None,'digest':sha_bytes((worktree_root/p).read_bytes()) if (worktree_root/p).exists() and (worktree_root/p).is_file() else 'missing'} for p in plan['changed_paths']]
      aggregate={'schema_version':RESULT_SCHEMA,'task_id':plan['task_id'],'attempt_id':plan['attempt_id'],'session_id':plan.get('implementation_session_id'),'implementation_session_id':plan.get('implementation_session_id'),'codex_thread_id':plan.get('codex_thread_id'),'implementation_result_digest':plan.get('implementation_result_digest'),'worktree_descriptor_digest':plan.get('worktree_descriptor_digest'),'change_manifest_digest':plan.get('change_manifest_digest'),'patch_digest':plan.get('patch_digest'),'base_sha':plan.get('terminal_worktree_head'),'changed_paths':plan.get('changed_paths',[]),'worktree_manifest':validated_manifest,'validation_ref_id':ref,'plan_digest':plan['plan_digest'],'command_result_digests':[r['result_digest'] for r in results],'required_stage_outcomes':[{ 'stage_id':r['stage_id'],'exit_code':r['exit_code'],'failure_class':r['failure_class']} for r in results],'skipped_stages':[],'total_duration_seconds':time.time()-start,'total_budget_consumed_seconds':sum(float(r['duration_seconds']) for r in results),'cumulative_task_validation_seconds':sum(float(r['duration_seconds']) for r in results),'source_drift_proof':{'before':before,'after':after,'source_drift_detected':failure_class=='source_drift'},'exhaustive_matrix_status':plan['exhaustive_matrix_status'],'matrix_invocation_count':0,'terminal_status':terminal,'failure_classification':failure_class,'correctable':correctable,'result_digest':'','journal_terminal_event_id':None}
      aggregate['result_digest']=seal(aggregate,'result_digest'); _write_immutable(state_root/'maintenance_validation_results'/(ref+'.json'),aggregate)
      if append_journal:
        etype='validation_passed' if terminal=='validation_ready_for_commit' else 'validation_failed'; payload={'validation_ref_id':ref,'attempt_id':plan['attempt_id'],'session_id':plan.get('implementation_session_id'),'plan_digest':plan['plan_digest'],'result_digest':aggregate['result_digest'],'change_manifest_digest':plan.get('change_manifest_digest'),'worktree_descriptor_digest':plan.get('worktree_descriptor_digest'),'terminal_status':terminal,'correctable':correctable}
        ar=journal.append_event(state_root,etype,task_id=plan['task_id'],payload=payload,event_id='mevent_'+hashlib.sha256(cj(payload)).hexdigest()[:32],repo_root=repository_root,recorded_at=evaluation_time)
        if ar.event: aggregate['journal_terminal_event_id']=ar.event.event_id
      return aggregate

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
    _write_immutable(state_root/'maintenance_validation_plans'/(plan['validation_ref_id']+'.json'),plan)
    result=run_validation_plan(state_root=state_root,repository_root=repository_root,
        worktree_root=Path(str(worktree['worktree_root'])),policy=policy,plan=plan,
        evaluation_time=evaluation_time)
    if result.get('terminal_status')=='validation_failed_correctable':
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
        _write_immutable(state_root/'maintenance_validation_plans'/(plan['validation_ref_id']+'.json'),plan)
        result=run_validation_plan(state_root=state_root,repository_root=repository_root,
            worktree_root=Path(str(worktree['worktree_root'])),policy=policy,plan=plan,
            evaluation_time=evaluation_time)
    if result.get('terminal_status')=='validation_ready_for_commit':
        payload={'validation_ref_id':plan['validation_ref_id'],'attempt_id':plan['attempt_id'],
                 'result_digest':result['result_digest'],'plan_digest':plan['plan_digest'],
                 'worktree_descriptor_digest':plan.get('worktree_descriptor_digest'),
                 'change_manifest_digest':plan.get('change_manifest_digest')}
        appended=journal.append_event(state_root,'ready_to_commit_recorded',task_id=plan['task_id'],
            payload=payload,event_id='mevent_'+hashlib.sha256(cj(payload)).hexdigest()[:32],
            repo_root=repository_root,recorded_at=evaluation_time)
        if appended.status not in {'event_appended','event_already_recorded'}:
            return {'status':'controller_integrity_failed','reason_code':appended.reason_code}
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
        if ns.cmd=='verify-result': r=read_json(Path(ns.plan)); ok=r.get('result_digest')==seal(r,'result_digest'); print(json.dumps({'status':'validation_result_verified' if ok else 'validation_result_invalid'},sort_keys=True)); return 0 if ok else 2
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
