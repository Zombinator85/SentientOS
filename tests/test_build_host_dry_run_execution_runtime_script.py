from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

import pytest
from sentientos.host_fulfillment_executor_readiness_runtime import HostFulfillmentExecutorReadinessRuntimeCoordinator
from tests.test_host_fulfillment_authorization_runtime import Kernel, consume, chain

pytestmark = pytest.mark.no_legacy_skip

def _write_source(tmp_path):
    issue,g,ver,led,exp,src,env=chain(); result=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    ev=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'hfer-state', kernel=Kernel(), clock=lambda:'2029-01-02T00:00:00+00:00').evaluate(result, output_root=tmp_path/'hfer-external', grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp)
    p=tmp_path/'source.json'; p.write_text(json.dumps(ev.to_dict(), sort_keys=True), encoding='utf-8'); return p

def test_help_invocations():
    assert subprocess.run(['./scripts/build_host_dry_run_execution_runtime.py','--help'], text=True, capture_output=True).returncode==0
    assert subprocess.run([sys.executable,'scripts/build_host_dry_run_execution_runtime.py','--help'], text=True, capture_output=True).returncode==0

def test_cli_validate_and_simulate_require_complete_bundle(tmp_path):
    source=_write_source(tmp_path)
    good=subprocess.run([sys.executable,'scripts/build_host_dry_run_execution_runtime.py','validate-source','--source',str(source)], text=True, capture_output=True)
    assert good.returncode==0 and json.loads(good.stdout)['ok'] is True
    sim=subprocess.run([sys.executable,'scripts/build_host_dry_run_execution_runtime.py','simulate','--source',str(source),'--output-root',str(tmp_path/'external')], text=True, capture_output=True)
    assert sim.returncode==0 and json.loads(sim.stdout)['status']=='dry_run_runtime_simulated'
    receipt=tmp_path/'receipt.json'; receipt.write_text(json.dumps(json.loads(source.read_text())['readiness_receipt']), encoding='utf-8')
    bad=subprocess.run([sys.executable,'scripts/build_host_dry_run_execution_runtime.py','validate-source','--source',str(receipt)], text=True, capture_output=True)
    assert bad.returncode!=0 and 'standalone_readiness_receipt_rejected' in bad.stderr
