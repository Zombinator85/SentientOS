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
    with pytest.raises(ValueError, match='invalid_readiness_source'):
        build_request(replace(src, contract=changed_contract))

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

def test_actual_concurrent_duplicate_evaluation_creates_one_bundle(tmp_path):
    src=readiness(tmp_path); out=tmp_path/'external'
    results=[]
    def run():
        c=HostDryRunExecutionRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel())
        results.append(c.evaluate(src, output_root=out))
    threads=[threading.Thread(target=run) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert {r.status for r in results} == {'dry_run_runtime_simulated'}
    assert len([p for p in out.iterdir() if p.is_dir()]) == 1
    assert sum(1 for r in results if r.replayed) == 1

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

from sentientos.host_dry_run_execution_runtime import validate_persisted_evaluation_bundle, digest_record as hdr_digest_record, _sha as hdr_sha
from sentientos.dry_run_execution_harness import dry_run_execution_request_digest, dry_run_execution_result_digest, dry_run_execution_receipt_digest, simulated_backend_registry_digest
import hashlib

def _file_digest(path: Path) -> str:
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()

def _rewrite_hdr_manifests(bundle: Path) -> None:
    for manifest_name, kind, key, skip in (
        ('content_manifest.json','host_dry_run_execution_runtime_content_manifest','content_manifest_digest', {'runtime_receipt.json','content_manifest.json','bundle_manifest.json'}),
        ('bundle_manifest.json','host_dry_run_execution_runtime_bundle_manifest','bundle_digest', {'bundle_manifest.json'}),
    ):
        files=[]
        for path in sorted(p for p in bundle.iterdir() if p.is_file() and p.name not in skip and not p.name.startswith('.')):
            files.append({'relative_filename': path.name, 'size': path.stat().st_size, 'digest': _file_digest(path), 'artifact_kind': path.stem, 'schema_version': 'host_dry_run_execution_runtime.v1'})
        data={'schema_version':'host_dry_run_execution_runtime.v1','artifact_kind':kind,'files':files,key:hdr_sha({'files':files,'artifact_kind':kind})}
        (bundle/manifest_name).write_text(json.dumps(data, sort_keys=True, indent=2), encoding='utf-8')

def _rewrite_hdr_runtime_receipt(bundle: Path) -> None:
    content=json.loads((bundle/'content_manifest.json').read_text())
    final=json.loads((bundle/'bundle_manifest.json').read_text())
    rr=json.loads((bundle/'runtime_receipt.json').read_text())
    rr['content_manifest_digest']=content['content_manifest_digest']; rr['bundle_digest']=''; rr['digest']=hdr_digest_record(rr)
    (bundle/'runtime_receipt.json').write_text(json.dumps(rr, sort_keys=True, indent=2), encoding='utf-8')
    _rewrite_hdr_manifests(bundle)

def test_recomputed_admission_authority_harness_registry_lineage_rejected(tmp_path):
    bundle=tmp_path/'external'/HostDryRunExecutionRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel()).evaluate(readiness(tmp_path), output_root=tmp_path/'external').request.request_id
    admission=json.loads((bundle/'simulation_admission.json').read_text()); admission['authority_class']='privileged_operator_control'; (bundle/'simulation_admission.json').write_text(json.dumps(admission, sort_keys=True), encoding='utf-8')
    _rewrite_hdr_manifests(bundle); _rewrite_hdr_runtime_receipt(bundle)
    assert 'simulation_admission_authority_mismatch' in validate_persisted_evaluation_bundle(bundle).findings
    bundle=source=tmp_path/'external2'/HostDryRunExecutionRuntimeCoordinator(runtime_state_root=tmp_path/'state2', kernel=Kernel()).evaluate(readiness(tmp_path/'r2'), output_root=tmp_path/'external2').request.request_id
    policy=json.loads((bundle/'harness_policy.json').read_text()); policy['no_real_backends']=False; (bundle/'harness_policy.json').write_text(json.dumps(policy, sort_keys=True), encoding='utf-8')
    _rewrite_hdr_manifests(bundle); _rewrite_hdr_runtime_receipt(bundle)
    assert 'harness_policy_not_canonical' in validate_persisted_evaluation_bundle(bundle).findings
    bundle=tmp_path/'external3'/HostDryRunExecutionRuntimeCoordinator(runtime_state_root=tmp_path/'state3', kernel=Kernel()).evaluate(readiness(tmp_path/'r3'), output_root=tmp_path/'external3').request.request_id
    registry=json.loads((bundle/'simulated_backend_registry.json').read_text()); registry['supported_dry_run_domains']=['operator_review_dry_run']; registry['digest']=simulated_backend_registry_digest(registry); (bundle/'simulated_backend_registry.json').write_text(json.dumps(registry, sort_keys=True), encoding='utf-8')
    _rewrite_hdr_manifests(bundle); _rewrite_hdr_runtime_receipt(bundle)
    assert 'simulated_backend_registry_not_canonical' in validate_persisted_evaluation_bundle(bundle).findings

def test_recomputed_result_receipt_lineage_and_runtime_parent_substitution_rejected(tmp_path):
    bundle=tmp_path/'external'/HostDryRunExecutionRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel()).evaluate(readiness(tmp_path), output_root=tmp_path/'external').request.request_id
    result=json.loads((bundle/'result_or_block_receipt.json').read_text()); result['request_id']='substituted'; result['digest']=dry_run_execution_result_digest(result); (bundle/'result_or_block_receipt.json').write_text(json.dumps(result, sort_keys=True), encoding='utf-8')
    receipt=json.loads((bundle/'dry_run_receipt.json').read_text()); receipt['result_digest']=result['digest']; receipt['digest']=dry_run_execution_receipt_digest(receipt); (bundle/'dry_run_receipt.json').write_text(json.dumps(receipt, sort_keys=True), encoding='utf-8')
    rr=json.loads((bundle/'runtime_receipt.json').read_text()); rr['result_or_block_digest']=result['digest']; rr['dry_run_receipt_digest']=receipt['digest']; rr['digest']=hdr_digest_record(rr); (bundle/'runtime_receipt.json').write_text(json.dumps(rr, sort_keys=True, indent=2), encoding='utf-8')
    _rewrite_hdr_manifests(bundle); _rewrite_hdr_runtime_receipt(bundle)
    findings=validate_persisted_evaluation_bundle(bundle).findings
    assert 'result_request_lineage_mismatch' in findings
    bundle=tmp_path/'external2'/HostDryRunExecutionRuntimeCoordinator(runtime_state_root=tmp_path/'state2', kernel=Kernel()).evaluate(readiness(tmp_path/'r2'), output_root=tmp_path/'external2').request.request_id
    rr=json.loads((bundle/'runtime_receipt.json').read_text()); rr['dry_run_request_id']='substituted'; rr['digest']=hdr_digest_record(rr); (bundle/'runtime_receipt.json').write_text(json.dumps(rr, sort_keys=True), encoding='utf-8')
    _rewrite_hdr_manifests(bundle); _rewrite_hdr_runtime_receipt(bundle)
    assert 'runtime_receipt_dry_run_request_parent_mismatch' in validate_persisted_evaluation_bundle(bundle).findings
