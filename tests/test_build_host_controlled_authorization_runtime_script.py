from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

def test_cli_plan_and_loose_evaluate_fail_closed():
    plan = subprocess.run([sys.executable, 'scripts/build_host_controlled_authorization_runtime.py', 'plan'], text=True, capture_output=True, check=True)
    assert json.loads(plan.stdout)['metadata_only'] is True
    ev = subprocess.run([sys.executable, 'scripts/build_host_controlled_authorization_runtime.py', 'evaluate', '--input', 'missing.json'], text=True, capture_output=True)
    assert ev.returncode == 2
    assert json.loads(ev.stdout)['host_mutation_performed'] is False

def test_cli_validate_bundle_and_render(tmp_path):
    bundle = {'runtime_plan': {}, 'admission_reference': {}, 'source_evidence_manifest': {}, 'controlled_authorization_contracts': [], 'schema_grant_records': [], 'revocation_schemas': [], 'authorization_ledgers': [], 'typed_safety_evidence_manifests': [], 'safety_gate_assessments': [], 'safety_gate_satisfaction_manifests': [], 'summary': {'status': 'ok'}}
    path = tmp_path/'bundle.json'; path.write_text(json.dumps(bundle), encoding='utf-8')
    ok = subprocess.run([sys.executable, 'scripts/build_host_controlled_authorization_runtime.py', 'validate-bundle', '--input', str(path)], text=True, capture_output=True, check=True)
    assert json.loads(ok.stdout)['ok'] is True
    md = subprocess.run([sys.executable, 'scripts/build_host_controlled_authorization_runtime.py', 'render-markdown', '--input', str(path)], text=True, capture_output=True, check=True)
    assert 'Live authorization granted' in md.stdout
