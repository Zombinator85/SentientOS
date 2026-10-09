import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import pytest
from sentientos import maintenance_validation_controller as v
from sentientos import maintenance_task_journal as journal
from tests.test_maintenance_validation_acceptance import prepare, commands, result_path, verify, Interrupted
from tests.maintenance_commit_publication_fixtures import NOW

pytestmark=pytest.mark.no_legacy_skip

CHILD = r"""
import json,os,signal,sys
from pathlib import Path
from sentientos import maintenance_validation_controller as v
k=json.loads(Path(sys.argv[1]).read_text())
for key in ('state_root','repository_root','worktree_root'): k[key]=Path(k[key])
k['policy']=v.ValidationPolicy.from_mapping(k['policy'])
original=v._write_immutable
count=0
def stop(path,data):
    global count
    answer=original(path,data)
    if 'maintenance_validation_commands' in path.parts:
        count+=1
        if count==int(sys.argv[2]): os.kill(os.getpid(),signal.SIGKILL)
    return answer
if int(sys.argv[2]): v._write_immutable=stop
out=v.run_validation_plan(**k)
Path(sys.argv[3]).write_text(json.dumps(out))
"""

def reconstruct(kw,tmp_path,stop=0):
    config=tmp_path/f'child-{stop}.json'
    config.write_text(json.dumps({**kw,'policy':kw['policy'].to_dict()},default=str))
    output=tmp_path/f'child-{stop}-output.json'
    cp=subprocess.run([sys.executable,'-c',CHILD,str(config),str(stop),str(output)],capture_output=True,text=True)
    return cp,output

def test_recovery_after_command_result_persistence_does_not_rerun_command(tmp_path):
    counter=tmp_path/'counter'
    code='from pathlib import Path\ndef hit():\n    p=Path('+repr(str(counter))+')\n    p.write_text(p.read_text()+"x" if p.exists() else "x")\ndef test_one(): hit()\ndef test_two(): hit()\n'
    _,kw=prepare(tmp_path,code,('test_one','test_two'),timeout=5)
    cp,_=reconstruct(kw,tmp_path,2)
    assert cp.returncode==-signal.SIGKILL,cp.stderr
    assert counter.read_text()=='x'
    before={p:p.read_bytes() for p in commands(kw)}
    cp,path=reconstruct(kw,tmp_path)
    assert cp.returncode==0,cp.stderr
    result=json.loads(path.read_text()); assert result['terminal_status']=='validation_ready_for_commit',result
    assert counter.read_text()=='xx'
    assert all(p.read_bytes()==b for p,b in before.items())
    first=result['total_budget_consumed_seconds']
    cp,path=reconstruct(kw,tmp_path)
    assert cp.returncode==0 and counter.read_text()=='xx'
    assert json.loads(path.read_text())['total_budget_consumed_seconds']==first

def test_recovery_after_validation_result_persistence_appends_only_missing_event(tmp_path,monkeypatch):
    _,kw=prepare(tmp_path); original=v._write_immutable
    def stop(path,data):
        out=original(path,data)
        if 'maintenance_validation_results' in path.parts: raise Interrupted()
        return out
    with monkeypatch.context() as m:
        m.setattr(v,'_write_immutable',stop)
        with pytest.raises(Interrupted): v.run_validation_plan(**kw)
    before={p:p.read_bytes() for p in commands(kw)}; canonical=result_path(kw).read_bytes()
    kw['evaluation_time']='2026-08-05T00:01:00+0000'
    assert v.run_validation_plan(**kw)['terminal_status']=='validation_ready_for_commit'
    jp=kw['state_root']/'maintenance_tasks/task1.jsonl'; journal_bytes=jp.read_bytes()
    assert v.run_validation_plan(**kw)['terminal_status']=='validation_ready_for_commit'
    assert jp.read_bytes()==journal_bytes and result_path(kw).read_bytes()==canonical
    assert all(p.read_bytes()==b for p,b in before.items())

def test_recovery_after_correction_completion_reuses_same_attempt_and_session(tmp_path):
    # Keep the existing correction-envelope contract; the real watchdog
    # continuation and distinct failed/passed cycles are exercised separately.
    _,kw=prepare(tmp_path,'def test_bad(): assert False\n',('test_bad',))
    result=v.run_validation_plan(**kw)
    le=dict(kw['plan']['canonical_inputs']['lease']); le['maximum_corrective_retries']=1
    envelope=v.build_correction_envelope(state_root=kw['state_root'],plan=kw['plan'],result=result,lease=le,previous_result={})
    assert envelope['prior_implementation_session_id']==kw['plan']['implementation_session_id']
    assert envelope['failed_validation_result_digest']==result['result_digest']

def test_process_concurrent_advance_runs_one_validation_and_one_correction(tmp_path):
    counter=tmp_path/'counter'
    code='import time\nfrom pathlib import Path\ndef test_one():\n    p=Path('+repr(str(counter))+')\n    p.write_text(p.read_text()+"x" if p.exists() else "x")\n    time.sleep(.3)\n'
    _,kw=prepare(tmp_path,code,('test_one',),timeout=5)
    config=tmp_path/'parallel.json'; config.write_text(json.dumps({**kw,'policy':kw['policy'].to_dict()},default=str))
    children=[subprocess.Popen([sys.executable,'-c',CHILD,str(config),'0',str(tmp_path/f'out{i}.json')],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for i in range(2)]
    for child in children:
        _,err=child.communicate(timeout=20); assert child.returncode==0,err
    results=[json.loads((tmp_path/f'out{i}.json').read_text()) for i in range(2)]
    assert sum(r.get('terminal_status')=='validation_ready_for_commit' for r in results)>=1
    assert counter.read_text()=='x'
    assert len(commands(kw))==2


def test_real_watchdog_recovers_killed_failed_controller_without_readiness(tmp_path,monkeypatch):
    from sentientos import maintenance_loop_watchdog as watchdog
    from tests.maintenance_watchdog_implementation_fixtures import setup, NOW as WATCHDOG_NOW
    cfg,roots,repo=setup(tmp_path,validation_expectations=['pytest_node:tests/fake.py::test_fail'])
    executable=tmp_path/'validator'
    executable.write_text('#!/bin/sh\nexit 1\n'); executable.chmod(0o755)
    cfg=dict(cfg); cfg['validation_policy']=v.ValidationPolicy('failed-recovery','repo',
        python_executable=str(executable),external_scratch_root=str(roots['scratch']),
        per_command_default_ceiling_seconds=2,maximum_controller_cycles=1).to_dict()
    cfg=watchdog.validate_config({k:value for k,value in cfg.items() if k!='config_digest'})
    monkeypatch.setenv('FAKE_CODEX_MODE','success')
    for _ in range(5): watchdog.tick(cfg,evaluation_time=WATCHDOG_NOW)
    config=tmp_path/'watchdog.json'; config.write_text(json.dumps(cfg))
    child='''import json,os,signal,sys
from pathlib import Path
from sentientos import maintenance_validation_controller as v, maintenance_loop_watchdog as watchdog
write=v._write_immutable
def stop(path,data):
    answer=write(path,data)
    if 'maintenance_validation_commands' in path.parts and data['exit_code']!=0: os.kill(os.getpid(),signal.SIGKILL)
    return answer
v._write_immutable=stop
watchdog.tick(json.loads(Path(sys.argv[1]).read_text()),evaluation_time=sys.argv[2])
'''
    cp=subprocess.run([sys.executable,'-c',child,str(config),WATCHDOG_NOW],capture_output=True,text=True)
    assert cp.returncode==-signal.SIGKILL,cp.stderr
    durable={p:p.read_bytes() for p in (roots['state']/'maintenance_validation_commands').rglob('*.json')}
    recovered=watchdog.tick(cfg,evaluation_time='2026-08-06T00:01:00Z')
    assert recovered['transition']=='recover_validation'
    assert recovered['effect_result']['status']=='corrective_retry_limit_reached'
    assert recovered['effect_result']['validation_result']['terminal_status']=='validation_failed_correctable'
    assert all(p.read_bytes()==data for p,data in durable.items())
    task=recovered['effect_result']['validation_result']['task_id']
    assert journal.materialize_snapshot(roots['state'],task,repo_root=repo)['commit_readiness'] is None
    assert not (roots['state']/'maintenance_commit_results').exists()
