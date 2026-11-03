from __future__ import annotations
import pytest
pytestmark = pytest.mark.no_legacy_skip
import time
from pathlib import Path

from sentientos.control_plane_kernel import ControlPlaneKernel, LifecyclePhase
from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass, ControlActionRequest
from sentientos.host_collectors import HostCollectorResult
from sentientos.host_resource_runtime import HostObservationBudget, HostObservationCollectorSpec, HostResourceRuntimeCoordinator, build_observation_plan, default_collector_specs, persist_evidence_bundle, redact_value, validate_evaluation, world_state_records
from sentientos.runtime_governor import RuntimeGovernor


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


def test_default_observation_plan_includes_optional_nvidia_telemetry() -> None:
    plan = build_observation_plan()
    gpu_collectors = [item for item in plan.collectors if item.collector_id == "nvidia_gpu"]

    assert len(gpu_collectors) == 1
    assert gpu_collectors[0].required is False
    assert len(plan.collectors) <= plan.budget.max_collectors
    assert plan.effect_authority is False


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


def test_host_pressure_defers_background_inference_and_recovers_without_reserving_admission(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor, phase=LifecyclePhase.MAINTENANCE, decisions_path=tmp_path / "kernel.jsonl")
    no_evidence_background = ControlActionRequest(
        action_kind="local_model_inference",
        authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE,
        actor="maintenance",
        target_subsystem="local_model",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"purpose": "maintenance_implementation", "correlation_id": "retry-after-missing-evidence"},
    )
    kernel.set_phase(LifecyclePhase.RUNTIME)
    no_evidence = kernel.admit(no_evidence_background)
    assert no_evidence.outcome == AdmissionOutcome.DEFER
    assert "runtime_governor:deferred_resource_telemetry_incomplete" in no_evidence.reason_codes
    kernel.set_phase(LifecyclePhase.MAINTENANCE)

    def collectors(cpu_percent: float):
        return build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1, lambda observed_at=None: _result("cpu", utilization_percent=cpu_percent)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2, lambda observed_at=None: _result("memory", used_percent=50.0)),
            HostObservationCollectorSpec("disk", True, ("linux", "unknown"), 3, lambda observed_at=None: _result("disk", used_percent=20.0, free_bytes=1000)),
        ])

    pressured = HostResourceRuntimeCoordinator(kernel=kernel, runtime_state_root=tmp_path / "pressure", plan=collectors(95.0)).run_cycle(correlation_id="pressure")
    assert pressured is not None and validate_evaluation(pressured).ok
    assert kernel.observe_host_resource_evaluation(pressured)
    kernel.set_phase(LifecyclePhase.RUNTIME)
    background = ControlActionRequest(
        action_kind="local_model_inference",
        authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE,
        actor="maintenance",
        target_subsystem="local_model",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"purpose": "maintenance_implementation", "correlation_id": "retry-after-pressure"},
    )
    deferred = kernel.admit(background)
    assert deferred.outcome == AdmissionOutcome.DEFER
    assert "runtime_governor:deferred_background_inference_under_host_pressure" in deferred.reason_codes

    kernel.set_phase(LifecyclePhase.MAINTENANCE)
    nominal = HostResourceRuntimeCoordinator(kernel=kernel, runtime_state_root=tmp_path / "nominal", plan=collectors(20.0)).run_cycle(correlation_id="nominal")
    assert nominal is not None and kernel.observe_host_resource_evaluation(nominal)
    kernel.set_phase(LifecyclePhase.RUNTIME)
    recovered = kernel.admit(background)
    assert recovered.outcome == AdmissionOutcome.ALLOW
    runtime_decision = recovered.delegated_outcomes["runtime_governor"]
    assert runtime_decision["evidence_refs"]["host_resource_evidence"]["evaluation_id"] == nominal.evaluation_id
    assert kernel.admit(no_evidence_background).outcome == AdmissionOutcome.ALLOW

    foreground = ControlActionRequest(
        action_kind="local_model_inference",
        authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE,
        actor="user",
        target_subsystem="local_model",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"purpose": "local_user_chat", "correlation_id": "foreground-pressure"},
    )
    # Foreground chat is not mislabeled as background work when the collector
    # reports pressure; its independent invocation limits still apply.
    assert kernel.observe_host_resource_evaluation(pressured)
    assert kernel.admit(foreground).outcome == AdmissionOutcome.ALLOW


def test_nvml_gpu_pressure_reaches_background_inference_admission(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.0")
    kernel = ControlPlaneKernel(
        runtime_governor=RuntimeGovernor(),
        phase=LifecyclePhase.MAINTENANCE,
        decisions_path=tmp_path / "kernel.jsonl",
    )
    plan = build_observation_plan(specs=[
        HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                                     lambda observed_at=None: _result("cpu", utilization_percent=20.0)),
        HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                                     lambda observed_at=None: _result("memory", used_percent=40.0)),
        HostObservationCollectorSpec("disk", True, ("linux", "unknown"), 3,
                                     lambda observed_at=None: _result("disk", used_percent=30.0, free_bytes=1000)),
        HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 4,
                                     lambda observed_at=None: _result(
                                         "nvidia_gpu", device_count=1,
                                         devices=[{"index": 0, "gpu_utilization_percent": 95.0,
                                                   "vram_utilization_percent": 92.0}]))
    ])

    evaluation = HostResourceRuntimeCoordinator(
        kernel=kernel, runtime_state_root=tmp_path / "resources", plan=plan,
    ).run_cycle(correlation_id="gpu-pressure")
    assert evaluation is not None and validate_evaluation(evaluation).ok
    assert evaluation.snapshot.gpu_utilization_percent == 95.0
    assert evaluation.snapshot.vram_utilization_percent == 92.0
    assert "gpu_pressure" in evaluation.pressure_report.pressure_labels
    assert kernel.observe_host_resource_evaluation(evaluation)

    kernel.set_phase(LifecyclePhase.RUNTIME)
    request = ControlActionRequest(
        action_kind="local_model_inference",
        authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE,
        actor="maintenance",
        target_subsystem="local_model",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"purpose": "maintenance_implementation", "correlation_id": "gpu-pressure-inference"},
    )
    decision = kernel.admit(request)
    assert decision.outcome == AdmissionOutcome.DEFER
    assert "runtime_governor:deferred_background_inference_under_host_pressure" in decision.reason_codes
    resource_evidence = decision.delegated_outcomes["runtime_governor"]["evidence_refs"]["host_resource_evidence"]
    assert resource_evidence["gpu_utilization_percent"] == 95.0
    assert resource_evidence["vram_utilization_percent"] == 92.0


def test_gpu_offloaded_inference_requires_gpu_telemetry_and_recovers(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.0")
    kernel = ControlPlaneKernel(
        runtime_governor=RuntimeGovernor(), phase=LifecyclePhase.MAINTENANCE,
        decisions_path=tmp_path / "kernel.jsonl",
    )

    def resource_plan(include_gpu: bool):
        specs = [
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                lambda observed_at=None: _result("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                lambda observed_at=None: _result("memory", used_percent=40.0)),
            HostObservationCollectorSpec("disk", True, ("linux", "unknown"), 3,
                lambda observed_at=None: _result("disk", used_percent=30.0, free_bytes=1000)),
        ]
        if include_gpu:
            specs.append(HostObservationCollectorSpec("nvidia_gpu", False,
                ("linux", "unknown"), 4, lambda observed_at=None: _result(
                    "nvidia_gpu", device_count=1,
                    devices=[{"index": 0, "gpu_utilization_percent": 15.0,
                              "vram_utilization_percent": 35.0}])))
        return build_observation_plan(specs=specs)

    def observe(correlation_id: str, include_gpu: bool):
        evaluation = HostResourceRuntimeCoordinator(
            kernel=kernel, runtime_state_root=tmp_path / correlation_id,
            plan=resource_plan(include_gpu),
        ).run_cycle(correlation_id=correlation_id)
        assert evaluation is not None and validate_evaluation(evaluation).ok
        assert kernel.observe_host_resource_evaluation(evaluation)
        return evaluation

    profile_digest = "a" * 64
    gpu_profile = {"schema_version": "sentientos.model_execution_profile:v1",
                   "engine": "llama_cpp", "accelerator_route": "gpu",
                   "gpu_layers": 16,
                   "configuration_digest": profile_digest}
    cpu_profile = {**gpu_profile, "accelerator_route": "cpu", "gpu_layers": 0}

    missing_gpu = observe("missing-gpu", include_gpu=False)
    assert missing_gpu.snapshot.gpu_utilization_percent is None
    kernel.set_phase(LifecyclePhase.RUNTIME)
    cpu_only = kernel.admit(ControlActionRequest(
        action_kind="local_model_inference", authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE,
        actor="maintenance", target_subsystem="local_model",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"purpose": "maintenance_implementation", "correlation_id": "cpu-profile",
                  "model_execution_profile": cpu_profile},
    ))
    assert cpu_only.outcome == AdmissionOutcome.ALLOW
    gpu_without_measurement = kernel.admit(ControlActionRequest(
        action_kind="local_model_inference", authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE,
        actor="maintenance", target_subsystem="local_model",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"purpose": "maintenance_implementation", "correlation_id": "gpu-profile-missing",
                  "model_execution_profile": gpu_profile},
    ))
    assert gpu_without_measurement.outcome == AdmissionOutcome.DEFER
    assert "runtime_governor:deferred_gpu_offload_telemetry_incomplete" in gpu_without_measurement.reason_codes

    kernel.set_phase(LifecyclePhase.MAINTENANCE)
    measured_gpu = observe("gpu-measured", include_gpu=True)
    assert measured_gpu.snapshot.gpu_utilization_percent == 15.0
    assert measured_gpu.snapshot.vram_utilization_percent == 35.0
    kernel.set_phase(LifecyclePhase.RUNTIME)
    gpu_with_measurement = kernel.admit(ControlActionRequest(
        action_kind="local_model_inference", authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE,
        actor="maintenance", target_subsystem="local_model",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"purpose": "maintenance_implementation", "correlation_id": "gpu-profile-ready",
                  "model_execution_profile": gpu_profile},
    ))
    assert gpu_with_measurement.outcome == AdmissionOutcome.ALLOW
    evidence = gpu_with_measurement.delegated_outcomes["runtime_governor"]["evidence_refs"]["host_resource_evidence"]
    assert evidence["gpu_telemetry_available"] is True
    assert evidence["gpu_utilization_percent"] == 15.0
