import os
from pathlib import Path
import subprocess
import pytest
from sentientos import maintenance_validation_controller as v
from tests.test_maintenance_validation_acceptance import prepare, commands, verify

pytestmark = pytest.mark.no_legacy_skip

def test_passing_validation_records_ready_for_commit_status(tmp_path):
    _,kw=prepare(tmp_path); result=v.run_validation_plan(**kw)
    assert result['terminal_status']=='validation_ready_for_commit'
    assert verify(kw)['result']==result

def test_failed_validator_records_immutable_failure_result(tmp_path):
    _,kw=prepare(tmp_path,'def test_bad():\n    assert False\n',('test_bad',))
    result=v.run_validation_plan(**kw)
    assert result['terminal_status']=='validation_failed_correctable'
    assert result['correctable'] is True and result['command_result_digests']
    before={p:p.read_bytes() for p in commands(kw)}
    assert v.run_validation_plan(**kw)==result
    assert all(p.read_bytes()==data for p,data in before.items())

def test_validation_timeout_terminates_child_and_grandchild(tmp_path):
    pidfile=tmp_path/'grandchild.pid'
    code="import subprocess,sys,time\nfrom pathlib import Path\ndef test_slow():\n    p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\n    Path("+repr(str(pidfile))+").write_text(str(p.pid))\n    time.sleep(30)\n"
    _,kw=prepare(tmp_path,code,('test_slow',),timeout=2)
    result=v.run_validation_plan(**kw)
    assert result['terminal_status']=='validation_timed_out',result
    assert pidfile.exists(), 'The timeout must reach the actual grandchild witness'
    pid=int(pidfile.read_text()); status=Path(f'/proc/{pid}/stat')
    assert not status.exists() or status.read_text().split()[2]=='Z'

def test_timeout_remains_timeout_when_child_exits_zero(tmp_path):
    code='import os,signal,time\ndef test_slow():\n    signal.signal(signal.SIGTERM,lambda *a:os._exit(0))\n    time.sleep(30)\n'
    _,kw=prepare(tmp_path,code,('test_slow',),timeout=2)
    result=v.run_validation_plan(**kw)
    assert result['terminal_status']=='validation_timed_out'
    assert result['required_stage_outcomes'][-1]['exit_code']==0
    assert v.run_validation_plan(**kw)['terminal_status']=='validation_timed_out'

def test_validation_source_drift_fails_closed(tmp_path):
    code="from pathlib import Path\ndef test_drift():\n    Path('a.txt').write_text('drift\\n')\n"
    _,kw=prepare(tmp_path,code,('test_drift',))
    result=v.run_validation_plan(**kw)
    assert result['terminal_status']=='validation_workspace_changed_during_proof',result
    assert result['source_drift_proof']['source_drift_detected'] is True

def test_validation_commands_use_argv_without_command_interpreter(tmp_path,monkeypatch):
    _,kw=prepare(tmp_path); seen=[]; original=subprocess.Popen
    def spy(argv,*args,**kwargs):
        seen.append((argv,kwargs.get('shell')))
        return original(argv,*args,**kwargs)
    monkeypatch.setattr(subprocess,'Popen',spy)
    assert v.run_validation_plan(**kw)['terminal_status']=='validation_ready_for_commit'
    assert seen and all(isinstance(a,list) and shell is False for a,shell in seen)
