import subprocess, sys

def test_diagnose_json() -> None:
    proc=subprocess.run([sys.executable,'scripts/codex_strict_audit_repair.py','diagnose','--summary'],capture_output=True,text=True,check=False)
    assert proc.returncode==0
    assert 'status' in proc.stdout

def test_repair_refuses_without_allow() -> None:
    proc=subprocess.run([sys.executable,'scripts/codex_strict_audit_repair.py','repair','--strict-output','AGENTS.md'],capture_output=True,text=True,check=False)
    assert proc.returncode in {2,4}
