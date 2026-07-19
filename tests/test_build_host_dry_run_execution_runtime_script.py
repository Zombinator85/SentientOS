from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

import pytest
from sentientos.host_fulfillment_executor_readiness_runtime import HostFulfillmentExecutorReadinessRuntimeCoordinator
from tests.test_host_fulfillment_authorization_runtime import Kernel, consume, chain
from tests.test_host_fulfillment_executor_readiness_runtime import _snapshot_for
from sentientos.local_authorization_grant import build_local_authorization_grant_expiry_evaluation, build_local_authorization_grant_ledger, verify_local_authorization_grant

pytestmark = pytest.mark.no_legacy_skip

def _write_source(tmp_path):
    issue,g,ver,led,exp,src,env=chain(); result=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    later_exp=build_local_authorization_grant_expiry_evaluation(g, evaluated_at='2029-01-02T00:00:00+00:00')
    later_ver=verify_local_authorization_grant(g, checked_scope_labels=g.granted_scope_labels, checked_time_label='2029-01-02T00:00:00+00:00', expiry_evaluation=later_exp)
    later_led=build_local_authorization_grant_ledger((g,), (), (later_exp,), created_at='2029-01-02T00:00:00+00:00')
    snap=_snapshot_for(g,later_led,src)
    ev=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'hfer-state', kernel=Kernel(), clock=lambda:'2029-01-02T00:00:00+00:00').evaluate(result, output_root=tmp_path/'hfer-external', grant=g, verification=later_ver, current_snapshot=snap, expiry_evaluation=later_exp)
    p=tmp_path/'source.json'; p.write_text(json.dumps(ev.to_dict(), sort_keys=True), encoding='utf-8')
    sp=tmp_path/'snapshot.json'; sp.write_text(json.dumps(snap.to_dict(), sort_keys=True), encoding='utf-8')
    vp=tmp_path/'verification.json'; vp.write_text(json.dumps(later_ver.to_dict(), sort_keys=True), encoding='utf-8')
    return p, tmp_path/'hfer-external'/ev.request.request_id, sp, vp

def test_help_invocations():
    assert subprocess.run(['./scripts/build_host_dry_run_execution_runtime.py','--help'], text=True, capture_output=True).returncode==0
    assert subprocess.run([sys.executable,'scripts/build_host_dry_run_execution_runtime.py','--help'], text=True, capture_output=True).returncode==0

def test_cli_validate_and_simulate_require_complete_bundle(tmp_path):
    source,bundle,snapshot,verification=_write_source(tmp_path)
    good=subprocess.run([sys.executable,'scripts/build_host_dry_run_execution_runtime.py','validate-source','--readiness-bundle-root',str(bundle),'--current-snapshot',str(snapshot),'--current-verification',str(verification)], text=True, capture_output=True)
    assert good.returncode==0 and json.loads(good.stdout)['ok'] is True
    sim=subprocess.run([sys.executable,'scripts/build_host_dry_run_execution_runtime.py','simulate','--readiness-bundle-root',str(bundle),'--current-snapshot',str(snapshot),'--current-verification',str(verification),'--output-root',str(tmp_path/'external')], text=True, capture_output=True)
    assert sim.returncode==0 and json.loads(sim.stdout)['status'] in {'blocked_dry_run_runtime','dry_run_runtime_simulated'}
    assert json.loads(sim.stdout)['admission_call_count'] == 1
    plain=subprocess.run([sys.executable,'scripts/build_host_dry_run_execution_runtime.py','simulate','--source',str(source),'--output-root',str(tmp_path/'plain')], text=True, capture_output=True)
    assert plain.returncode!=0 and 'readiness-bundle-root' in plain.stderr
    receipt=tmp_path/'receipt.json'; receipt.write_text(json.dumps(json.loads(source.read_text())['readiness_receipt']), encoding='utf-8')
    bad=subprocess.run([sys.executable,'scripts/build_host_dry_run_execution_runtime.py','validate-source','--source',str(receipt)], text=True, capture_output=True)
    assert bad.returncode!=0 and 'standalone_readiness_receipt_rejected' in bad.stderr
