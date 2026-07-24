from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
import pytest
from tests.test_host_real_effect_admission_runtime import closure_bundle
pytestmark = pytest.mark.no_legacy_skip

def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, 'scripts/build_host_real_effect_admission_runtime.py', *args], text=True, capture_output=True)

def test_cli_evaluate_validate_and_latest_summary(tmp_path: Path):
    source=closure_bundle(tmp_path); out=tmp_path/'out'
    proc=run('evaluate','--closure-bundle-root',str(source),'--output-root',str(out),'--admission-domain','diagnostics_real_effect_candidate')
    assert proc.returncode == 0, proc.stderr + proc.stdout
    data=json.loads(proc.stdout); assert data['status'] == 'host_real_effect_admission_runtime_recorded'
    assert run('validate-source','--closure-bundle-root',str(source)).returncode == 0
    assert run('validate-bundle','--output-root',str(out)).returncode == 0
    latest=run('latest-summary','--output-root',str(out))
    assert latest.returncode == 0 and json.loads(latest.stdout)['status'] == 'host_real_effect_admission_runtime_recorded'

def test_cli_invalid_validation_exits_nonzero(tmp_path: Path):
    bad=tmp_path/'bad'; bad.mkdir()
    assert run('validate-source','--closure-bundle-root',str(bad)).returncode != 0
    assert run('validate-bundle','--bundle',str(bad)).returncode != 0
