from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
from tests.test_host_dry_run_audit_closure_runtime import source_bundle

def run(*args: str):
    return subprocess.run([sys.executable, 'scripts/build_host_dry_run_audit_closure_runtime.py', *args], text=True, capture_output=True, check=True)

def test_help_entrypoints():
    assert 'host dry-run audit closure' in run('--help').stdout.lower()
    assert '--dry-run-runtime-bundle-root' in run('close-audit', '--help').stdout

def test_cli_close_validate_render(tmp_path):
    source=source_bundle(tmp_path); out=tmp_path/'closure'
    data=json.loads(run('close-audit', '--dry-run-runtime-bundle-root', str(source), '--output-root', str(out)).stdout)
    assert data['status'] == 'host_dry_run_audit_closure_runtime_closed'
    assert json.loads(run('validate-bundle', '--output-root', str(out)).stdout)['ok'] is True
    assert json.loads(run('summarize', '--output-root', str(out)).stdout)['metadata_only'] is True
    assert '# Host Dry-Run Audit Closure Runtime' in run('render-markdown', '--output-root', str(out)).stdout
    assert json.loads(run('diff').stdout)['simulation_only'] is True
