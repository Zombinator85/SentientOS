from __future__ import annotations
from dataclasses import replace
import json, threading

import pytest
from sentientos.control_plane_kernel import AdmissionOutcome
from sentientos.host_fulfillment_executor_readiness_runtime import HostFulfillmentExecutorReadinessRuntimeCoordinator, build_request, dashboard_projection, validate_consumption_source, world_state_records
from tests.test_host_fulfillment_authorization_runtime import Kernel, consume

pytestmark = pytest.mark.no_legacy_skip

def test_exact_typed_consumption_builds_review_package_without_authority(tmp_path):
    result=consume(tmp_path/'hfac')
    c=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel(), clock=lambda:'2029-01-02T00:00:00+00:00')
    ev=c.evaluate(result, output_root=tmp_path/'external')
    assert ev.status=='ready_for_executor_contract_review_with_conditions'
    assert ev.builder_call_count==6 and ev.admission_call_count==1 and ev.persisted is True
    assert ev.contract['source_consumption_receipt_digest']==result.consumption_receipt['digest']
    assert ev.backend_declaration['contract_digest']==ev.contract['digest']
    assert ev.precondition_manifest['contract_digest']==ev.contract['digest']
    assert ev.precondition_manifest['source_consumption_receipt_digest']==result.consumption_receipt['digest']
    assert ev.dry_run_plan['contract_digest']==ev.contract['digest']
    assert ev.admission_packet['contract_digest']==ev.contract['digest']
    assert ev.admission_packet['backend_declaration_digest']==ev.backend_declaration['digest']
    assert ev.admission_packet['precondition_manifest_digest']==ev.precondition_manifest['digest']
    assert ev.admission_packet['dry_run_plan_digest']==ev.dry_run_plan['digest']
    assert ev.readiness_receipt['admission_packet_digest']==ev.admission_packet['digest']
    for key,val in ev.runtime_receipt.no_authority.items(): assert val is False
    assert ev.backend_declaration['backend_loaded'] is False
    assert ev.dry_run_plan['dry_run_executed'] is False
    assert ev.admission_packet['control_plane_admission_granted'] is False
    assert ev.readiness_receipt['executor_implemented'] is False
    assert any(p.status=='missing' for p in ev.prerequisite_records)

def test_loose_or_denied_or_tampered_sources_fail_strict(tmp_path):
    result=consume(tmp_path/'hfac')
    assert validate_consumption_source(result).ok
    denied=replace(result, status='denied')
    assert 'denial_only_result_rejected' in validate_consumption_source(denied).findings
    no_receipt=replace(result, consumption_receipt=None)
    assert 'missing_successful_consumption_receipt' in validate_consumption_source(no_receipt).findings
    bad=replace(result, consumption_receipt={**result.consumption_receipt,'digest':'sha256:bad'})
    assert 'consumption_receipt_digest_unverified' in validate_consumption_source(bad).findings
    entry={**result.ledger_entry,'consumption_receipt':{**result.consumption_receipt,'digest':'sha256:bad'}}
    assert 'ledger_entry_receipt_mismatch' in validate_consumption_source(replace(result, ledger_entry=entry)).findings
    ledger={**result.ledger,'entries':[]}
    assert 'ledger_missing_exact_entry' in validate_consumption_source(replace(result, ledger=ledger)).findings

def test_metadata_admission_non_allow_zero_builder_calls(tmp_path):
    result=consume(tmp_path/'hfac')
    for outcome in (AdmissionOutcome.DENY, AdmissionOutcome.DEFER, AdmissionOutcome.QUARANTINE):
        k=Kernel(outcome); c=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/outcome.value, kernel=k)
        ev=c.evaluate(result, output_root=tmp_path/(outcome.value+'-out'))
        assert ev.status=='blocked_contract_package'
        assert ev.builder_call_count==0 and c.builder_call_count==0
        assert 'metadata_admission_not_allowed' in ev.findings

def test_current_grant_posture_blocks_without_rewriting_consumption(tmp_path):
    result=consume(tmp_path/'hfac')
    for posture in ('expired','revoked','stale','contradicted','unavailable'):
        ev=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/posture, kernel=Kernel()).evaluate(result, output_root=tmp_path/(posture+'-out'), current_grant_posture=posture)
        assert ev.status=='blocked_contract_package' and ev.builder_call_count==0
        assert result.consumption_receipt is not None

def test_backend_label_safety_and_timestamp_semantics(tmp_path):
    result=consume(tmp_path/'hfac')
    c=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel())
    assert 'backend_label_rejected' in c.evaluate(result, output_root=tmp_path/'out', backend_label='../evil').findings
    r1=build_request(result, created_at='2029-01-01T00:00:00+00:00')
    r2=build_request(result, created_at='2030-01-01T00:00:00+00:00')
    assert r1.request_id==r2.request_id and r1.digest==r2.digest

def test_world_state_and_dashboard_projection_are_review_only(tmp_path):
    result=consume(tmp_path/'hfac')
    ev=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel()).evaluate(result, output_root=tmp_path/'external')
    records=world_state_records(ev)
    assert records and {r['stage'] for r in records} <= {'proposal','review','admission'}
    proj=dashboard_projection(records)
    assert proj['read_only'] is True and proj['execution_ready'] is False and proj['backend_invoked'] is False and proj['effect_performed'] is False
    assert proj['contract_package_count'] >= 1

def test_repository_local_root_rejected_and_no_git_or_host_mutation(tmp_path):
    result=consume(tmp_path/'hfac')
    ev=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel()).evaluate(result, output_root='runtime_artifacts')
    assert 'repository_local_runtime_root_rejected' in ev.findings
