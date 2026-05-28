from __future__ import annotations
import json, subprocess
from pathlib import Path

FIX=Path('tests/fixtures/household_presence_camera_capture_review_packet/valid_design_review_packet.json')

def _run(*args:str)->subprocess.CompletedProcess[str]:
    return subprocess.run(['python','scripts/build_household_presence_camera_capture_review_packet.py',*args],text=True,capture_output=True,check=False)

def test_commands_work():
    assert _run('build-default').returncode==0
    assert _run('validate').returncode==0
    assert _run('inspect-fixture','--fixture-name','valid_design_review_packet.json').returncode==0
    assert _run('evaluate','--input',str(FIX)).returncode==0
    out=_run('summarize','--input',str(FIX)); assert out.returncode==0; assert 'capture_review_packet_ready_for_operator_review' in out.stdout

def test_blocked_nonzero():
    f=Path('/tmp/missing_auth.json'); p=json.loads(FIX.read_text()); p['authorization_envelope_digest']=''; f.write_text(json.dumps(p))
    assert _run('evaluate','--input',str(f)).returncode!=0
