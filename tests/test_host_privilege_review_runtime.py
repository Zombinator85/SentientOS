from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import pytest

from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass, ControlActionDecision, ControlPlaneKernel, LifecyclePhase
from sentientos.host_collectors import HostCollectorResult
from sentientos.host_resource_runtime import HostObservationCollectorSpec, HostResourceRuntimeCoordinator, build_observation_plan
from sentientos.host_privilege_review_runtime import HostPrivilegeReviewRuntimeCoordinator, persist_evidence_bundle, validate_evaluation, world_state_records
from sentientos.privilege_broker import build_privilege_broker_review_receipt, evaluate_privilege_broker_eligibility, privilege_broker_receipt_digest
from sentientos.actuation_fulfillment import build_actuation_fulfillment_rehearsal_receipt, build_actuation_fulfillment_plan

pytestmark = pytest.mark.no_legacy_skip

def _result(cid: str, status: str = "available", **values):
    return HostCollectorResult(cid, status, "2026-01-01T00:00:00+00:00", "test", values=values)

def _host_eval(tmp_path):
    plan = build_observation_plan(specs=[
        HostObservationCollectorSpec("memory", True, ("linux","unknown"), 1, lambda observed_at=None: _result("memory", "available", total_bytes=100, available_bytes=10, used_percent=90)),
        HostObservationCollectorSpec("disk", True, ("linux","unknown"), 2, lambda observed_at=None: _result("disk", "available", used_percent=95, free_bytes=1)),
        HostObservationCollectorSpec("cpu", True, ("linux","unknown"), 3, lambda observed_at=None: _result("cpu", "available", utilization_percent=95)),
    ])
    c = HostResourceRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path, plan=plan)
    e = c.run_cycle(correlation_id="tick:host")
    assert e is not None and e.proposal_receipts
    return e, c

def test_same_in_memory_evaluation_no_rerun_and_complete_linkage(tmp_path):
    host_eval, host_coord = _host_eval(tmp_path)
    c = HostPrivilegeReviewRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    ev = c.run_cycle(tick_id="tick", source_evaluation=host_eval, persist=True)
    assert ev is not None
    assert ev.source_host_evaluation_id == host_eval.evaluation_id
    assert host_coord.collector_call_count == 3
    assert c.builder_call_count == len(ev.items) * 4
    assert validate_evaluation(ev).ok
    for item in ev.items:
        if item.valid_source:
            assert item.broker_decision.source_receipt_digest == item.source_receipt_digest
            assert item.broker_review_receipt.source_receipt_digest == item.source_receipt_digest
            assert item.fulfillment_plan.source_broker_receipt_digest == item.broker_review_receipt.digest
            assert item.fulfillment_rehearsal_receipt.source_broker_receipt_digest == item.broker_review_receipt.digest
            assert not item.fulfillment_plan.authorization_granted
            assert not item.fulfillment_rehearsal_receipt.effect_not_performed is False

def test_non_allow_admission_zero_builder_calls_and_duplicate_correlation(tmp_path):
    host_eval, _ = _host_eval(tmp_path)
    c = HostPrivilegeReviewRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    deny = ControlActionDecision(AdmissionOutcome.DENY, ("test",), LifecyclePhase.MAINTENANCE, LifecyclePhase.MAINTENANCE, AuthorityClass.PROPOSAL_EVALUATION, "host_privilege_review_rehearsal_runtime", "test", "host_privilege_review_rehearsal_runtime", {}, "corr")
    assert c.run_cycle(tick_id="deny", source_evaluation=host_eval, decision=deny) is None
    assert c.builder_call_count == 0
    ok = c.run_cycle(tick_id="ok", source_evaluation=host_eval, correlation_id="same")
    again = c.run_cycle(tick_id="other", source_evaluation=host_eval, correlation_id="same")
    assert ok is again
    assert c.builder_call_count == (len(ok.items) * 4 if ok else 0)

def test_malformed_receipt_contained_and_conflicting_duplicate_fails_closed(tmp_path):
    host_eval, _ = _host_eval(tmp_path)
    r = host_eval.proposal_receipts[0]
    bad = replace(r, receipt_id="dup", digest="bad")
    conflict = replace(r, receipt_id="dup", proposal_kind="future_cooling_policy_candidate", digest="other")
    tampered_eval = replace(host_eval, proposal_receipts=(bad, conflict) + host_eval.proposal_receipts[1:])
    c = HostPrivilegeReviewRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    ev = c.run_cycle(tick_id="tamper", source_evaluation=tampered_eval)
    assert ev is not None
    assert any(not i.valid_source for i in ev.items)
    assert any("duplicate_receipt_id_conflicting_digest" in i.findings or "receipt_digest_mismatch" in i.findings for i in ev.items)
    assert any(i.valid_source for i in ev.items)

def test_timestamp_independent_semantic_identity_and_semantic_change_changes_identity(tmp_path):
    host_eval, _ = _host_eval(tmp_path)
    receipt = host_eval.proposal_receipts[0]
    d = evaluate_privilege_broker_eligibility(receipt)
    a = build_privilege_broker_review_receipt(d, created_at="2026-01-01T00:00:00+00:00")
    b = build_privilege_broker_review_receipt(d, created_at="2030-01-01T00:00:00+00:00")
    assert a.receipt_id == b.receipt_id
    assert a.digest == b.digest
    p = build_actuation_fulfillment_plan(a)
    ra = build_actuation_fulfillment_rehearsal_receipt(p, created_at="2026-01-01T00:00:00+00:00")
    rb = build_actuation_fulfillment_rehearsal_receipt(p, created_at="2030-01-01T00:00:00+00:00")
    assert ra.receipt_id == rb.receipt_id and ra.digest == rb.digest
    changed = replace(a, blocked_actions=a.blocked_actions + ("new_block",), digest="")
    assert privilege_broker_receipt_digest(changed) != a.digest

def test_atomic_bundle_and_world_state_no_effect_projection(tmp_path):
    host_eval, _ = _host_eval(tmp_path)
    c = HostPrivilegeReviewRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    ev = c.run_cycle(tick_id="bundle", source_evaluation=host_eval)
    assert ev is not None
    receipt = persist_evidence_bundle(tmp_path, ev, tick_id="bundle")
    assert Path(receipt.artifact_paths["summary"]).exists()
    records = world_state_records(ev)
    assert {r["stage"] for r in records} <= {"proposal", "review"}
    assert all(r["effect_claimed"] is False and r["effect_proven"] is False and r["host_mutation_performed"] is False for r in records)
