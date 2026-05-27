from __future__ import annotations
import subprocess, sys

def _run(*args:str)->subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable,'scripts/build_household_presence_camera_capture_denial_ledger.py',*args],text=True,capture_output=True,check=False)

def test_build_default(): assert _run('build-default').returncode==0

def test_evaluate_fixture():
    p='tests/fixtures/household_presence_camera_capture_denial_ledger/missing_operator_grant_denial.json'
    assert _run('evaluate','--input',p).returncode==0
