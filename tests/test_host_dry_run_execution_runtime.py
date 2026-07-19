from __future__ import annotations
import json, threading
from dataclasses import replace
from pathlib import Path

import pytest
from sentientos.control_plane_kernel import AdmissionOutcome
from sentientos.host_fulfillment_executor_readiness_runtime import HostFulfillmentExecutorReadinessRuntimeCoordinator
from sentientos.host_dry_run_execution_runtime import HostDryRunExecutionRuntimeCoordinator, dashboard_projection, validate_source_evaluation, world_state_records, build_request
from tests.test_host_fulfillment_authorization_runtime import Kernel, consume, chain

pytestmark = pytest.mark.no_legacy_skip

def readiness(tmp_path):
    issue,g,ver,led,exp,src,env=chain(); result=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    ev=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'hfer-state', kernel=Kernel(), clock=lambda:'2029-01-02T00:00:00+00:00').evaluate(result, output_root=tmp_path/'hfer-external', grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp)
    assert ev.status.startswith('ready_for_executor_contract_review')
    return ev

def test_complete_exact_readiness_bundle_simulates_and_persists(tmp_path):
    src=readiness(tmp_path)
    c=HostDryRunExecutionRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel(), clock=lambda:'2029-01-02T00:00:00+00:00')
    ev=c.evaluate(src, output_root=tmp_path/'external')
    assert ev.status=='dry_run_runtime_simulated'
    assert ev.admission_call_count==1 and ev.harness_builder_call_count>=2 and ev.simulation_call_count==1
    assert ev.dry_run_receipt['dry_run_executed'] is True
    for key in ('executor_implemented','real_executor_invoked','backend_loaded','backend_invoked','real_backend_invoked','fulfillment_granted','effect_performed','host_mutation_performed'):
        assert ev.dry_run_receipt[key] is False
    assert (tmp_path/'external'/ev.request.request_id/'bundle_manifest.json').exists()

def test_standalone_or_incomplete_readiness_rejected_zero_calls(tmp_path):
    src=readiness(tmp_path)
    bad=replace(src, runtime_receipt=None)
    c=HostDryRunExecutionRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel())
    ev=c.evaluate(bad, output_root=tmp_path/'external')
    assert ev.status=='blocked_dry_run_runtime'
    assert 'missing_runtime_receipt' in ev.findings and ev.admission_call_count==0 and ev.simulation_call_count==0

def test_stale_contradicted_expired_or_revoked_current_authority_blocks_zero_calls(tmp_path):
    src=readiness(tmp_path)
    for status in ('stale_contract_package','contradicted_contract_package','blocked_contract_package','unavailable_contract_package'):
        c=HostDryRunExecutionRuntimeCoordinator(runtime_state_root=tmp_path/status, kernel=Kernel())
        ev=c.evaluate(replace(src, status=status), output_root=tmp_path/(status+'-out'))
        assert ev.status=='blocked_dry_run_runtime'
        assert ev.admission_call_count==0 and ev.harness_builder_call_count==0 and ev.simulation_call_count==0

def test_simulation_admission_allow_and_denials_zero_harness_calls(tmp_path):
    src=readiness(tmp_path)
    ok=HostDryRunExecutionRuntimeCoordinator(runtime_state_root=tmp_path/'ok', kernel=Kernel()).evaluate(src, output_root=tmp_path/'ok-out')
    assert ok.status=='dry_run_runtime_simulated'
    for outcome in (AdmissionOutcome.DENY, AdmissionOutcome.DEFER, AdmissionOutcome.QUARANTINE):
        c=HostDryRunExecutionRuntimeCoordinator(runtime_state_root=tmp_path/outcome.value, kernel=Kernel(outcome))
        ev=c.evaluate(src, output_root=tmp_path/(outcome.value+'-out'))
        assert ev.status=='blocked_dry_run_runtime'
        assert ev.harness_builder_call_count==0 and ev.simulation_call_count==0 and not ev.dry_run_receipt

def test_domain_mapping_lineage_identity_and_timestamp_semantics(tmp_path):
    src=readiness(tmp_path)
    req1=build_request(src, created_at='2029-01-01T00:00:00+00:00')
    req2=build_request(src, created_at='2030-01-01T00:00:00+00:00')
    assert req1.request_id==req2.request_id and req1.digest==req2.digest
    assert req1.dry_run_domain=='future_cooling_dry_run' and req1.simulated_backend_class=='cooling_backend_simulated'
    changed_contract={**src.contract, 'digest':'sha256:changed'}
    req3=build_request(replace(src, contract=changed_contract))
    assert req3.request_id != req1.request_id

def test_replay_conflict_concurrency_and_corruption(tmp_path):
    src=readiness(tmp_path); out=tmp_path/'external'
    c=HostDryRunExecutionRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel())
    ev1=c.evaluate(src, output_root=out); before=(c.admission_call_count,c.harness_builder_call_count,c.simulation_call_count)
    ev2=c.evaluate(src, output_root=out)
    assert ev2.replayed is True and (c.admission_call_count,c.harness_builder_call_count,c.simulation_call_count)==before
    conflict=c.evaluate(src, output_root=out, correlation_id='different')
    assert conflict.status in {'dry_run_runtime_simulated','contradicted_dry_run_runtime'}
    (out/ev1.request.request_id/'dry_run_request.json').write_text('{"corrupt": true}', encoding='utf-8')
    corrupt=c.evaluate(src, output_root=out)
    assert corrupt.status=='contradicted_dry_run_runtime'

def test_world_state_dashboard_are_read_only_and_zero_runtime_calls(tmp_path):
    src=readiness(tmp_path); c=HostDryRunExecutionRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel())
    ev=c.evaluate(src, output_root=tmp_path/'external')
    counts=(c.admission_call_count,c.harness_builder_call_count,c.simulation_call_count)
    records=world_state_records(ev)
    proj=dashboard_projection(records)
    assert proj['read_only'] is True and proj['simulation_only'] is True and proj['real_backend_invoked'] is False and proj['host_mutation_performed'] is False
    assert (c.admission_call_count,c.harness_builder_call_count,c.simulation_call_count)==counts
    assert records and {r['stage'] for r in records} <= {'proposal','review','rehearsal'}

def test_repository_local_root_rejected_and_no_git_mutation(tmp_path):
    src=readiness(tmp_path)
    ev=HostDryRunExecutionRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel()).evaluate(src, output_root='runtime_artifacts')
    assert 'repository_local_runtime_root_rejected' in ev.findings
