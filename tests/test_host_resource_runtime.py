from __future__ import annotations
import pytest
pytestmark = pytest.mark.no_legacy_skip
import time
from pathlib import Path

from sentientos.control_plane_kernel import ControlPlaneKernel, LifecyclePhase
from sentientos.host_collectors import HostCollectorResult
from sentientos.host_resource_runtime import HostObservationBudget, HostObservationCollectorSpec, HostResourceRuntimeCoordinator, build_observation_plan, default_collector_specs, persist_evidence_bundle, redact_value, validate_evaluation, world_state_records


def _result(cid: str, status: str = "available", **values):
    return HostCollectorResult(cid, status, "2026-01-01T00:00:00+00:00", "test", values=values)


def test_denial_defer_quarantine_call_zero_collectors(tmp_path):
    calls = {"n": 0}
    def collector(*, observed_at=None):
        calls["n"] += 1; return _result("x")
    plan = build_observation_plan(specs=[HostObservationCollectorSpec("x", True, ("linux","unknown"), 1, collector)])
    # Runtime phase mismatches maintenance request -> defer before any call.
    c = HostResourceRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.RUNTIME), runtime_state_root=tmp_path, plan=plan)
    assert c.run_cycle(correlation_id="deny") is None
    assert calls["n"] == 0
    # Malformed duplicate/non-string metadata is not reachable through coordinator, but direct kernel quarantine also calls no collector.
    q = c.kernel.admit(type("Bad", (), {"action_kind":"", "actor":"", "target_subsystem":"", "metadata": {}, "requested_phase": LifecyclePhase.MAINTENANCE, "authority_class": __import__("sentientos.control_plane_kernel", fromlist=["AuthorityClass"]).AuthorityClass.OBSERVATION})())
    assert q.outcome.value in {"quarantine", "defer", "deny"}
    assert calls["n"] == 0


def test_duplicate_correlation_and_one_epoch_per_tick(tmp_path):
    calls = {"n": 0}
    def collector(*, observed_at=None): calls.__setitem__("n", calls["n"] + 1); return _result("x")
    plan = build_observation_plan(specs=[HostObservationCollectorSpec("x", True, ("linux","unknown"), 1, collector)])
    c = HostResourceRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path, plan=plan)
    a = c.run_cycle(correlation_id="tick:1"); b = c.run_cycle(correlation_id="tick:1")
    assert a is b
    assert calls["n"] == 1


def test_timeout_exception_partial_failure_and_late_discard(tmp_path):
    def ok(*, observed_at=None): return _result("ok", used_percent=0)
    def boom(*, observed_at=None): raise RuntimeError("/home/alice secret Traceback")
    def slow(*, observed_at=None): time.sleep(.2); return _result("slow")
    plan = build_observation_plan(budget=HostObservationBudget(per_collector_timeout_seconds=.01, total_deadline_seconds=.05, max_workers=2), specs=[HostObservationCollectorSpec("ok", True, ("linux","unknown"), 1, ok), HostObservationCollectorSpec("boom", False, ("linux","unknown"), 2, boom), HostObservationCollectorSpec("slow", False, ("linux","unknown"), 3, slow)])
    c = HostResourceRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path, plan=plan)
    e = c.run_cycle(correlation_id="tick:timeout")
    assert e is not None
    assert any(r.collector_id == "boom" and r.status == "error" for r in e.epoch.results)
    assert "slow" in e.epoch.timed_out_collectors or any(r.collector_id == "slow" and r.values.get("timeout") for r in e.epoch.results)
    assert not any("Traceback" in repr(r.to_dict()) or "/home/" in repr(r.to_dict()) for r in e.epoch.results)


def test_validation_redaction_identity_and_semantics(tmp_path):
    raw = {"path": "/workspace/SentientOS/x", "interfaces": [{"name": "eth0", "address": "aa:bb:cc:dd:ee:ff"}], "nested": {"env": "TOKEN=secret"}}
    redacted = redact_value(raw)
    assert "aa:bb" not in repr(redacted) and "/workspace" not in repr(redacted) and "TOKEN" not in repr(redacted)
    p1 = build_observation_plan(); p2 = build_observation_plan()
    assert p1.semantic_digest == p2.semantic_digest
    p3 = build_observation_plan(budget=HostObservationBudget(max_collectors=1))
    assert p1.semantic_digest != p3.semantic_digest


def test_evaluation_snapshot_policy_world_state_and_artifact_custody(tmp_path):
    c = HostResourceRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path, plan=build_observation_plan(specs=[HostObservationCollectorSpec("memory", True, ("linux","unknown"), 1, lambda observed_at=None: _result("memory", "partial", total_bytes=1, usage_unavailable=True)), HostObservationCollectorSpec("disk", True, ("linux","unknown"), 2, lambda observed_at=None: _result("disk", "available", used_percent=0, free_bytes=10)), HostObservationCollectorSpec("cpu", True, ("linux","unknown"), 3, lambda observed_at=None: _result("cpu", "partial", load_average_1m=0.0))]))
    e = c.run_cycle(correlation_id="tick:eval")
    assert e is not None
    assert e.snapshot.ram_utilization_percent is None  # unavailable is not zero
    assert "telemetry_incomplete" in e.pressure_report.pressure_labels or "sensor_unavailable" in e.pressure_report.pressure_labels
    assert e.policy_decision.proposal_only and not e.policy_decision.host_mutation_performed
    assert all(r.proposal_only and r.does_not_execute for r in e.proposal_receipts)
    assert validate_evaluation(e).ok
    receipt = persist_evidence_bundle(tmp_path, e, tick_id="tick:eval")
    assert Path(receipt.artifact_paths["summary"]).exists()
    records = world_state_records(e)
    assert {r["subject_id"] for r in records} >= {"host_resource_observation_epoch", "host_resource_pressure", "host_resource_policy"}
    assert all(r["effect_claimed"] is False and r["effect_proven"] is False for r in records)
