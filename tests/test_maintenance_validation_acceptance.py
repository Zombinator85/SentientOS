"""Real-command acceptance witnesses for failure-preserving validation custody."""
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys

import pytest

from sentientos import maintenance_validation_controller as v
from sentientos import maintenance_task_journal as journal
from tests.maintenance_commit_publication_fixtures import NOW, lease, produce_validation, repo, state

pytestmark = pytest.mark.no_legacy_skip


def prepare(tmp_path, code=None, nodes=(), timeout=3):
    r, w, base = repo(tmp_path, {'tests/test_probe.py': code} if code else None)
    s = state(tmp_path); le = lease(base=base); le['maximum_validation_seconds'] = 30
    policy = v.ValidationPolicy('acceptance', 'repo', python_executable=sys.executable,
        git_executable='/usr/bin/git', external_scratch_root=str(tmp_path/'scratch'),
        per_command_default_ceiling_seconds=timeout, terminal_reserve_seconds=.5)
    inputs = produce_validation(s, r, w, le, execute=False, policy=policy,
        expectations=['pytest_node:tests/test_probe.py::'+node for node in nodes] or ['git_diff_check'])
    plan = v.build_validation_plan(policy=policy, lease=le, implementation_result=inputs['implementation_result'],
        worktree=inputs['worktree'], change_manifest=inputs['change_manifest'])
    kwargs = dict(state_root=s, repository_root=r, worktree_root=w, policy=policy, plan=plan, evaluation_time=NOW)
    return inputs, kwargs


def reseal(path, mutate, field='result_digest'):
    data=json.loads(path.read_text()); mutate(data); data[field]=v.seal(data,field)
    path.write_bytes(v.cj(data)+b'\n'); return data


def result_path(kw):
    return kw['state_root']/'maintenance_validation_results'/(kw['plan']['validation_ref_id']+'.json')


def commands(kw):
    return sorted((kw['state_root']/'maintenance_validation_commands'/kw['plan']['validation_ref_id']).glob('*.json'))


def verify(kw, **extra):
    return v.verify_validation_evidence(state_root=kw['state_root'],repository_root=kw['repository_root'],
        validation_ref_id=kw['plan']['validation_ref_id'],evaluation_time=kw['evaluation_time'],**extra)


class Interrupted(BaseException):
    pass


@pytest.mark.parametrize('later', [False, True])
def test_durable_failure_never_becomes_ready_after_reconstruction(tmp_path, monkeypatch, later):
    _,kw=prepare(tmp_path,'def test_failure():\n    assert False\n',('test_failure',))
    original=v._write_immutable
    def interrupted(path,data):
        answer=original(path,data)
        if 'maintenance_validation_commands' in path.parts and data['exit_code']!=0:
            raise Interrupted()
        return answer
    with monkeypatch.context() as patch:
        patch.setattr(v,'_write_immutable',interrupted)
        with pytest.raises(Interrupted): v.run_validation_plan(**kw)
    before={str(p):p.read_bytes() for p in commands(kw)}
    if later: kw['evaluation_time']='2026-08-05T00:01:00+0000'
    recovered=v.run_validation_plan(**kw)
    assert recovered['terminal_status']=='validation_failed_correctable',recovered
    assert all(Path(p).read_bytes()==data for p,data in before.items())
    assert journal.materialize_snapshot(kw['state_root'],'task1',repo_root=kw['repository_root'])['commit_readiness'] is None
    with pytest.raises(ValueError,match='not_successful'): verify(kw)


@pytest.mark.parametrize('status,rc', [('timed_out',0),('timed_out',-15),('exited',-15),('exited',None),('exited',False),('exited','0'),('unknown',0)])
def test_completion_facts_cannot_be_relabelled_success(tmp_path,status,rc):
    _,kw=prepare(tmp_path); assert v.run_validation_plan(**kw)['terminal_status']=='validation_ready_for_commit'
    p=commands(kw)[0]
    reseal(p,lambda d:d.update(supervision_status=status,exit_code=rc,failure_class='passed'))
    with pytest.raises(ValueError): verify(kw)


@pytest.mark.parametrize('field,value', [('required_stage_outcomes',[]),('command_result_digests',[]),('skipped_stages',['required']),('total_budget_consumed_seconds',-1),('source_drift_proof',{}),('task_id','crossed'),('attempt_id','crossed'),('session_id','crossed'),('base_sha','crossed'),('correctable',True)])
def test_validly_resealed_aggregate_contradictions_are_denied(tmp_path,field,value):
    _,kw=prepare(tmp_path); v.run_validation_plan(**kw)
    reseal(result_path(kw),lambda d:d.update({field:value}))
    with pytest.raises(ValueError): verify(kw)


@pytest.mark.parametrize('damage', ['truncated','wrong_schema','bad_seal','missing','extra','symlink','start_missing','cycle_missing','context_missing'])
def test_corrupt_or_missing_custody_is_nonready(tmp_path,damage):
    _,kw=prepare(tmp_path); v.run_validation_plan(**kw); p=commands(kw)[0]
    if damage=='truncated': p.write_text('{')
    elif damage=='wrong_schema': reseal(p,lambda d:d.update(schema_version='legacy'))
    elif damage=='bad_seal': data=json.loads(p.read_text()); data['result_digest']='bad'; p.write_text(json.dumps(data))
    elif damage=='missing': p.unlink()
    elif damage=='extra': (p.parent/'extra.json').write_bytes(p.read_bytes())
    elif damage=='symlink': target=tmp_path/'substitute'; target.write_bytes(p.read_bytes()); p.unlink(); p.symlink_to(target)
    else:
        ref=kw['plan']['validation_ref_id']
        target=(kw['state_root']/'maintenance_validation_starts'/ref/p.name if damage=='start_missing'
                else kw['state_root']/('maintenance_validation_cycles' if damage=='cycle_missing' else 'maintenance_validation_contexts')/(ref+'.json'))
        target.unlink()
    with pytest.raises((ValueError,OSError)): verify(kw)


@pytest.mark.parametrize('field', ['task_id','lease_id','lease_digest','admitted_scope_digest','attempt_id','implementation_session_id','implementation_result_digest','validation_ref_id','validation_cycle_ordinal','policy_digest','worktree_descriptor_digest','change_manifest_digest','patch_digest','terminal_worktree_head'])
def test_independently_crossed_plan_bindings_fail_before_launch(tmp_path,monkeypatch,field):
    _,kw=prepare(tmp_path); plan=dict(kw['plan']); plan[field]=2 if field=='validation_cycle_ordinal' else 'crossed'
    plan['plan_digest']=v.seal(plan,'plan_digest'); kw['plan']=plan
    monkeypatch.setattr(v.subprocess,'Popen',lambda *a,**k:pytest.fail('command launched for crossed binding'))
    outcome=v.run_validation_plan(**kw)
    assert outcome['status']=='controller_integrity_failed'


@pytest.mark.parametrize('change', ['order','kind','argv','timeout','duplicate','required'])
def test_resealed_stage_plan_is_recomputed_from_policy(tmp_path,monkeypatch,change):
    _,kw=prepare(tmp_path,'def test_ok(): pass\n',('test_ok',))
    plan=json.loads(json.dumps(kw['plan'])); stages=plan['expanded_validation_stages']
    if change=='order': stages.reverse()
    elif change=='duplicate': stages.append(dict(stages[0]))
    else: stages[0]['timeout_seconds' if change=='timeout' else change]={'kind':'pytest_node','argv':['/bin/true'],'timeout':999,'required':False}[change]
    plan['plan_digest']=v.seal(plan,'plan_digest'); kw['plan']=plan
    monkeypatch.setattr(v.subprocess,'Popen',lambda *a,**k:pytest.fail('command launched for altered plan'))
    assert v.run_validation_plan(**kw)['status']=='controller_integrity_failed'


@pytest.mark.parametrize('mutation',['bytes','mode','addition','deletion','environment_value'])
def test_downtime_context_is_never_rebased(tmp_path,monkeypatch,mutation):
    _,kw=prepare(tmp_path); original=v._write_immutable
    def stop(path,data):
        out=original(path,data)
        if 'maintenance_validation_commands' in path.parts: raise Interrupted()
        return out
    with monkeypatch.context() as m:
        m.setattr(v,'_write_immutable',stop)
        with pytest.raises(Interrupted): v.run_validation_plan(**kw)
    target=kw['worktree_root']/'a.txt'
    if mutation=='bytes': target.write_text('changed during downtime\n')
    elif mutation=='mode': target.chmod(0o755)
    elif mutation=='addition': (kw['worktree_root']/'new.txt').write_text('x')
    elif mutation=='deletion': target.unlink()
    else: monkeypatch.setenv('LANG','C')
    outcome=v.run_validation_plan(**kw)
    assert outcome['status']=='controller_integrity_failed'
    assert not result_path(kw).exists()


def test_real_cli_success_uses_owner_custody(tmp_path):
    inputs,kw=prepare(tmp_path)
    files={name:tmp_path/(name+'.json') for name in ['plan','policy','worktree']}
    for name,value in [('plan',kw['plan']),('policy',kw['policy'].to_dict()),('worktree',inputs['worktree'])]:
        files[name].write_text(json.dumps(value))
    common=['--state-root',str(kw['state_root']),'--repository-root',str(kw['repository_root']),
        '--task-id','task1','--evaluation-time',NOW]
    cp=subprocess.run([sys.executable,'scripts/maintenance_validation_controller.py','validate',*common,
        '--plan',str(files['plan']),'--validation-policy',str(files['policy']),
        '--worktree-descriptor',str(files['worktree'])],text=True,capture_output=True,check=False)
    assert cp.returncode==0,cp.stdout+cp.stderr
    assert json.loads(cp.stdout)['terminal_status']=='validation_ready_for_commit'
    assert commands(kw) and json.loads(commands(kw)[0].read_text())['exit_code']==0
    args=[sys.executable,'scripts/maintenance_validation_controller.py','verify-result',
        '--state-root',str(kw['state_root']),'--repository-root',str(kw['repository_root']),
        '--task-id','task1','--evaluation-time',NOW,'--plan',str(result_path(kw))]
    cp=subprocess.run(args,text=True,capture_output=True,check=False)
    assert cp.returncode==0,cp.stdout+cp.stderr
    assert json.loads(cp.stdout)['semantic_readiness'] is True
    args[args.index('--task-id')+1]='another-task'
    crossed=subprocess.run(args,text=True,capture_output=True,check=False)
    assert crossed.returncode==2 and json.loads(crossed.stdout)['reason_code']=='cli_task_binding_mismatch'


def test_integrity_only_legacy_result_is_not_cli_readiness(tmp_path):
    path=tmp_path/'legacy.json'; value={'schema_version':'sentientos.maintenance_validation_result:v1','terminal_status':'validation_ready_for_commit'}
    value['result_digest']=v.seal(value,'result_digest'); path.write_text(json.dumps(value))
    cp=subprocess.run([sys.executable,'scripts/maintenance_validation_controller.py','verify-result',
        '--state-root',str(tmp_path),'--repository-root',str(tmp_path),'--task-id','t','--evaluation-time',NOW,'--plan',str(path)],capture_output=True,text=True)
    assert cp.returncode!=0
    assert json.loads(cp.stdout)=={'status':'validation_not_ready','integrity_valid':True,'semantic_readiness':False,'reason_code':"'validation_ref_id'"}


PERSISTENCE_BOUNDARIES={
    'plan':'maintenance_validation_plans','context':'maintenance_validation_contexts',
    'cycle':'maintenance_validation_cycles','stage_start':'maintenance_validation_starts',
    'command_result':'maintenance_validation_commands','aggregate':'maintenance_validation_results'}


@pytest.mark.parametrize('boundary',list(PERSISTENCE_BOUNDARIES)+['validation_started','terminal','readiness'])
@pytest.mark.parametrize('side',['before','after'])
def test_persistence_fault_matrix_reconstructs_disk_custody(tmp_path,monkeypatch,boundary,side):
    inputs,kw=prepare(tmp_path); write=v._write_immutable; event=v._event; fired=[]
    def interrupt(when):
        if when==side and not fired: fired.append(True); raise Interrupted()
    def wrapped_write(path,value):
        selected=PERSISTENCE_BOUNDARIES.get(boundary) in path.parts
        if selected: interrupt('before')
        out=write(path,value)
        if selected: interrupt('after')
        return out
    def wrapped_event(root,repo,plan,kind,payload,at,**kwargs):
        selected=kind=={'validation_started':'validation_started','terminal':'validation_passed','readiness':'ready_to_commit_recorded'}.get(boundary) and kwargs.get('append',True)
        if selected: interrupt('before')
        out=event(root,repo,plan,kind,payload,at,**kwargs)
        if selected: interrupt('after')
        return out
    with monkeypatch.context() as m:
        m.setattr(v,'_write_immutable',wrapped_write); m.setattr(v,'_event',wrapped_event)
        with pytest.raises(Interrupted): v.advance_validation_controller(**inputs)
    before={p:p.read_bytes() for p in commands(kw)}
    recovered=v.advance_validation_controller(**{**inputs,'evaluation_time':'2026-08-05T00:01:00+0000'})
    assert fired
    if (boundary=='stage_start' and side=='after') or (boundary=='command_result' and side=='before'):
        assert recovered['status']=='controller_integrity_failed'
        assert recovered['validation_result']['reason_code']=='indeterminate_stage_start'
    else:
        assert recovered['status']=='validation_ready_for_commit',recovered
        verify(kw)
    assert all(p.read_bytes()==data for p,data in before.items())


@pytest.mark.parametrize('boundary',['launch','exit','source_postcheck'])
@pytest.mark.parametrize('side',['before','after'])
def test_execution_fault_matrix_never_relaunches_indeterminate_stage(tmp_path,monkeypatch,boundary,side):
    _,kw=prepare(tmp_path); popen=v.subprocess.Popen; source=v._source; launched=[]; ended=[]; fired=[]
    def stop(when):
        if when==side and not fired: fired.append(True); raise Interrupted()
    def spawn(argv,*args,**kwargs):
        selected=argv==kw['plan']['expanded_validation_stages'][0]['argv']
        if selected and boundary=='launch': stop('before')
        proc=popen(argv,*args,**kwargs)
        if selected:
            launched.append(proc)
            communicate=proc.communicate
            def outcome(*a,**k):
                if boundary=='exit': stop('before')
                data=communicate(*a,**k); ended.append(True)
                if boundary=='exit': stop('after')
                return data
            proc.communicate=outcome
            if boundary=='launch': stop('after')
        return proc
    def postcheck(*args,**kwargs):
        if ended and boundary=='source_postcheck': stop('before')
        data=source(*args,**kwargs)
        if ended and boundary=='source_postcheck': stop('after')
        return data
    with monkeypatch.context() as m:
        m.setattr(v.subprocess,'Popen',spawn); m.setattr(v,'_source',postcheck)
        with pytest.raises(Interrupted): v.run_validation_plan(**kw)
    # Fixture cleanup only; the production recovery path gets no cleanup/retry authority.
    for proc in launched:
        proc.wait(timeout=10)
        if proc.stdout: proc.stdout.close()
        if proc.stderr: proc.stderr.close()
    result=v.run_validation_plan(**kw)
    assert result['status']=='controller_integrity_failed' and result['reason_code']=='indeterminate_stage_start'
    assert not commands(kw) and fired


@pytest.mark.parametrize('directory',list(PERSISTENCE_BOUNDARIES.values()))
@pytest.mark.parametrize('kind',['file_fsync','parent_fsync','write','flush'])
def test_durability_failure_is_explicit_and_retained(tmp_path,monkeypatch,directory,kind):
    _,kw=prepare(tmp_path); fsync=os.fsync; fdopen=os.fdopen; fired=[]
    def selected(fd):
        return directory in Path(os.readlink('/proc/self/fd/'+str(fd))).parts
    def fail_sync(fd):
        is_dir=Path('/proc/self/fd/'+str(fd)).is_dir()
        if selected(fd) and ((kind=='parent_fsync' and is_dir) or (kind=='file_fsync' and not is_dir)):
            fired.append(True); raise OSError('injected_durability_failure')
        return fsync(fd)
    class Output:
        def __init__(self,file): self.file=file
        def __enter__(self): return self
        def __exit__(self,*args): return self.file.__exit__(*args)
        def fileno(self): return self.file.fileno()
        def write(self,data):
            if kind=='write': self.file.write(data[:len(data)//2]); fired.append(True); raise OSError('injected_short_write')
            return self.file.write(data)
        def flush(self):
            if kind=='flush': fired.append(True); raise OSError('injected_flush')
            return self.file.flush()
    def opened(fd,*args,**kwargs):
        wrap=selected(fd) and kind in {'write','flush'}
        file=fdopen(fd,*args,**kwargs)
        return Output(file) if wrap else file
    with monkeypatch.context() as m:
        m.setattr(os,'fsync',fail_sync); m.setattr(os,'fdopen',opened)
        failed=v.run_validation_plan(**kw)
    assert fired and failed['status']=='controller_integrity_failed'
    before={p:p.read_bytes() for p in kw['state_root'].rglob('*.json')}
    recovered=v.run_validation_plan(**kw)
    assert recovered['status']=='controller_integrity_failed'
    assert all(p.read_bytes()==data for p,data in before.items())


@pytest.mark.parametrize('fault',['torn','conflict','append_failure','missing_predecessor','wrong_attempt'])
def test_journal_reconciliation_failures_cannot_confer_readiness(tmp_path,monkeypatch,fault):
    inputs,kw=prepare(tmp_path); original=v._write_immutable
    def stop(path,value):
        answer=original(path,value)
        if 'maintenance_validation_results' in path.parts: raise Interrupted()
        return answer
    with monkeypatch.context() as m:
        m.setattr(v,'_write_immutable',stop)
        with pytest.raises(Interrupted): v.run_validation_plan(**kw)
    path=kw['state_root']/'maintenance_tasks/task1.jsonl'
    if fault=='torn':
        with path.open('ab') as f: f.write(b'{')
    elif fault=='append_failure':
        monkeypatch.setattr(journal,'append_event',lambda *a,**k:journal.AppendResult('transition_rejected','injected',None,{}))
    elif fault=='conflict':
        result=journal.append_event(kw['state_root'],'validation_failed',task_id='task1',
            payload={'validation_ref_id':kw['plan']['validation_ref_id'],'attempt_id':'a1','result_digest':'contradictory'},repo_root=kw['repository_root'],recorded_at=NOW)
        assert result.status=='event_appended'
    elif fault=='missing_predecessor': path.unlink()
    else:
        # Altering an attempt without rebinding the plan is rejected before append.
        kw['plan']['attempt_id']='other'; kw['plan']['plan_digest']=v.seal(kw['plan'],'plan_digest')
    failed=v.run_validation_plan(**kw)
    assert failed['status']=='controller_integrity_failed'
    with pytest.raises((ValueError,OSError)): verify(kw)


def test_validator_replaced_at_same_path_is_denied_before_execution(tmp_path,monkeypatch):
    _,kw=prepare(tmp_path)
    executable=tmp_path/'git-proxy'
    executable.write_text('#!/bin/sh\nexec /usr/bin/git "$@"\n'); executable.chmod(0o755)
    policy=v.ValidationPolicy(**{**kw['policy'].__dict__,'git_executable':str(executable)})
    inputs=kw['plan']['canonical_inputs']; kw['policy']=policy
    kw['plan']=v.build_validation_plan(policy=policy,lease=inputs['lease'],implementation_result=inputs['implementation_result'],worktree=inputs['worktree'],change_manifest=inputs['change_manifest'])
    original=v._write_immutable
    def stop(path,data):
        answer=original(path,data)
        if 'maintenance_validation_commands' in path.parts: raise Interrupted()
        return answer
    with monkeypatch.context() as m:
        m.setattr(v,'_write_immutable',stop)
        with pytest.raises(Interrupted): v.run_validation_plan(**kw)
    executable.write_text('#!/bin/sh\nexit 97\n')
    monkeypatch.setattr(v.subprocess,'Popen',lambda *a,**k:pytest.fail('changed executable invoked'))
    assert v.run_validation_plan(**kw)['reason_code']=='execution_environment_changed'


def test_no_journal_diagnostic_validation_cannot_land(tmp_path):
    _,kw=prepare(tmp_path); result=v.run_validation_plan(**kw,append_journal=False)
    assert result['terminal_status']=='validation_ready_for_commit'
    with pytest.raises(ValueError,match='diagnostic_validation_not_authority'): verify(kw)


def test_prior_failed_cycle_budget_is_recomputed_from_commands(tmp_path,capsys):
    from tests.test_maintenance_watchdog_closed_loop import test_production_cli_process_real_fake_cycle_reaches_idle
    test_production_cli_process_real_fake_cycle_reaches_idle(tmp_path,capsys)
    s=tmp_path/'state'; r=tmp_path/'repo'
    results=[(p,json.loads(p.read_text())) for p in (s/'maintenance_validation_results').glob('*.json')]
    failed_path,failed=next((p,d) for p,d in results if d['terminal_status']=='validation_failed_correctable')
    _,passed=next((p,d) for p,d in results if d['terminal_status']=='validation_ready_for_commit')
    reseal(failed_path,lambda d:d.update(total_budget_consumed_seconds=0))
    with pytest.raises(ValueError,match='prior_cycle_semantic_contradiction'):
        v.verify_validation_evidence(state_root=s,repository_root=r,validation_ref_id=passed['validation_ref_id'],evaluation_time='2026-08-06T00:00:00Z')


def test_original_deadline_is_not_reset_before_untouched_stage(tmp_path,monkeypatch):
    _,kw=prepare(tmp_path,'def test_ok(): pass\n',('test_ok',)); write=v._write_immutable
    def stop(path,value):
        out=write(path,value)
        if 'maintenance_validation_commands' in path.parts: raise Interrupted()
        return out
    with monkeypatch.context() as m:
        m.setattr(v,'_write_immutable',stop)
        with pytest.raises(Interrupted): v.run_validation_plan(**kw)
    ref=kw['plan']['validation_ref_id']; context=json.loads((kw['state_root']/'maintenance_validation_contexts'/(ref+'.json')).read_text())
    monkeypatch.setattr(v.time,'time',lambda:context['created_at']+kw['plan']['aggregate_budget_seconds']+1)
    before={p:p.read_bytes() for p in commands(kw)}
    result=v.run_validation_plan(**kw)
    assert result['reason_code']=='original_cycle_budget_exhausted'
    assert {p:p.read_bytes() for p in commands(kw)}==before


@pytest.mark.parametrize('identity',['repository_root','worktree_root','same_path_directory_replacement'])
def test_actual_repository_and_worktree_substitution_is_not_recovery(tmp_path,monkeypatch,identity):
    _,kw=prepare(tmp_path); write=v._write_immutable
    def stop(path,value):
        out=write(path,value)
        if 'maintenance_validation_commands' in path.parts: raise Interrupted()
        return out
    with monkeypatch.context() as m:
        m.setattr(v,'_write_immutable',stop)
        with pytest.raises(Interrupted): v.run_validation_plan(**kw)
    if identity=='repository_root':
        other=tmp_path/'other-repository'; other.mkdir(); kw['repository_root']=other
    else:
        original=kw['worktree_root']; other=tmp_path/'other-worktree'
        if identity=='same_path_directory_replacement':
            original.rename(other); shutil.copytree(other,original)
        else:
            shutil.copytree(original,other); kw['worktree_root']=other
    result=v.run_validation_plan(**kw)
    assert result['status']=='controller_integrity_failed'
    assert result['reason_code'] in {'worktree_repository_lease_binding_mismatch','worktree_identity_mismatch','original_execution_context_changed'}
    assert not result_path(kw).exists()


@pytest.mark.parametrize('coverage',['duplicate','reordered','extra'])
def test_completed_stage_coverage_cannot_be_resealed(tmp_path,coverage):
    _,kw=prepare(tmp_path,'def test_ok(): pass\n',('test_ok',))
    assert v.run_validation_plan(**kw)['terminal_status']=='validation_ready_for_commit'
    def mutate(result):
        if coverage=='reordered':
            result['required_stage_outcomes'].reverse(); result['command_result_digests'].reverse()
        else:
            extra=dict(result['required_stage_outcomes'][0])
            if coverage=='extra': extra['stage_id']='unplanned-stage'
            result['required_stage_outcomes'].append(extra)
            result['command_result_digests'].append(result['command_result_digests'][0])
    reseal(result_path(kw),mutate)
    with pytest.raises(ValueError,match='aggregate_semantic_contradiction'): verify(kw)
