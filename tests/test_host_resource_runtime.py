from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timezone
import time
from pathlib import Path

import pytest
pytestmark = pytest.mark.no_legacy_skip

from sentientos.control_plane_kernel import ControlPlaneKernel, LifecyclePhase
from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass, ControlActionRequest
from sentientos.host_collectors import HostCollectorResult
from sentientos.host_resource_runtime import (MAX_RETAINED_OBSERVATION_EPOCHS,
    HostObservationBudget, HostObservationCollectorSpec, HostResourceRuntimeCoordinator,
    build_observation_plan, default_collector_specs, persist_evidence_bundle,
    redact_value, validate_evaluation, world_state_records)
from sentientos.game_performance_bridge import VerifiedGamePerformanceObservation
from sentientos.runtime_governor import RuntimeGovernor


def _result(cid: str, status: str = "available", **values):
    return HostCollectorResult(cid, status, "2026-01-01T00:00:00+00:00", "test", values=values)


def test_runtime_observation_is_read_only_and_quarantine_calls_no_collector(tmp_path):
    calls = {"n": 0}
    def collector(*, observed_at=None):
        calls["n"] += 1; return _result("x")
    plan = build_observation_plan(specs=[HostObservationCollectorSpec("x", True, ("linux","unknown"), 1, collector)])
    # Runtime monitoring is admitted in the kernel's current phase, but carries
    # no effect authority. A malformed direct request is still quarantined.
    c = HostResourceRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.RUNTIME), runtime_state_root=tmp_path, plan=plan)
    evaluation = c.run_cycle(correlation_id="runtime-observation")
    assert evaluation is not None
    assert evaluation.no_effect_authority is True
    assert c.collector_call_count == 1
    assert calls["n"] == 1
    # Malformed duplicate/non-string metadata is not reachable through coordinator, but direct kernel quarantine also calls no collector.
    q = c.kernel.admit(type("Bad", (), {"action_kind":"", "actor":"", "target_subsystem":"", "metadata": {}, "requested_phase": LifecyclePhase.MAINTENANCE, "authority_class": __import__("sentientos.control_plane_kernel", fromlist=["AuthorityClass"]).AuthorityClass.OBSERVATION})())
    assert q.outcome.value in {"quarantine", "defer", "deny"}
    assert calls["n"] == 1


def test_observation_rejects_admission_decision_from_another_kernel(tmp_path):
    calls = {"n": 0}

    def collector(*, observed_at=None):
        calls["n"] += 1
        return _result("memory", used_percent=20.0)

    plan = build_observation_plan(specs=[HostObservationCollectorSpec(
        "memory", True, ("linux", "unknown"), 1, collector)])
    owner_kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
        phase=LifecyclePhase.RUNTIME)
    other_kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
        phase=LifecyclePhase.RUNTIME)
    coordinator = HostResourceRuntimeCoordinator(
        kernel=owner_kernel, runtime_state_root=tmp_path, plan=plan)
    foreign_decision = other_kernel.admit(ControlActionRequest(
        action_kind="host_resource_observation_epoch",
        authority_class=AuthorityClass.OBSERVATION,
        actor="sentientosd",
        target_subsystem="host_resource_observation_runtime",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"correlation_id": "foreign-observation", "no_effect_authority": True},
    ))

    assert foreign_decision.allowed
    assert coordinator.run_cycle(
        correlation_id="foreign-observation", decision=foreign_decision) is None
    assert calls["n"] == 0

    owned_decision = coordinator.request_admission("owned-observation")
    evaluation = coordinator.run_cycle(
        correlation_id="owned-observation", decision=owned_decision)
    assert evaluation is not None and validate_evaluation(evaluation).ok
    assert calls["n"] == 1
    assert owner_kernel._runtime_governor._host_resource_evidence is not None
    assert other_kernel.observe_host_resource_evaluation(evaluation) is False
    assert other_kernel._runtime_governor._host_resource_evidence is None


def test_duplicate_correlation_and_one_epoch_per_tick(tmp_path):
    calls = {"n": 0}
    def collector(*, observed_at=None): calls.__setitem__("n", calls["n"] + 1); return _result("x")
    plan = build_observation_plan(specs=[HostObservationCollectorSpec("x", True, ("linux","unknown"), 1, collector)])
    c = HostResourceRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path, plan=plan)
    a = c.run_cycle(correlation_id="tick:1"); b = c.run_cycle(correlation_id="tick:1")
    assert a is b
    assert calls["n"] == 1


def test_observation_owner_bounds_process_local_epoch_cache(tmp_path):
    plan = build_observation_plan(specs=[HostObservationCollectorSpec(
        "memory", True, ("linux", "unknown"), 1,
        lambda observed_at=None: _result("memory", used_percent=20.0))])
    kernel = ControlPlaneKernel(phase=LifecyclePhase.RUNTIME,
        decisions_path=tmp_path / "kernel.jsonl")
    coordinator = HostResourceRuntimeCoordinator(
        kernel=kernel, runtime_state_root=tmp_path / "resources", plan=plan)

    for index in range(MAX_RETAINED_OBSERVATION_EPOCHS + 2):
        assert coordinator.run_cycle(correlation_id=f"tick-{index}") is not None

    assert len(coordinator._epochs_by_correlation) == MAX_RETAINED_OBSERVATION_EPOCHS
    assert "tick-0" not in coordinator._epochs_by_correlation


def test_latest_evaluation_is_fresh_cached_and_nonblocking(tmp_path):
    now = [datetime(2026, 11, 12, tzinfo=timezone.utc)]
    plan = build_observation_plan(specs=[HostObservationCollectorSpec(
        "memory", True, ("linux", "unknown"), 1,
        lambda observed_at=None: _result("memory", used_percent=20.0))])
    coordinator = HostResourceRuntimeCoordinator(
        kernel=ControlPlaneKernel(phase=LifecyclePhase.RUNTIME),
        runtime_state_root=tmp_path, plan=plan,
        clock=lambda: now[0].isoformat())

    assert coordinator.latest_evaluation() is None
    completed = coordinator.run_cycle(correlation_id="before-frame-pressure")
    assert completed is not None
    assert coordinator.latest_evaluation() is completed

    now[0] = now[0].replace(second=16)
    assert coordinator.latest_evaluation() is None
    now[0] = datetime(2026, 11, 12, tzinfo=timezone.utc)
    assert coordinator._cycle_lock.acquire(blocking=False)
    try:
        assert coordinator.latest_evaluation() is None
    finally:
        coordinator._cycle_lock.release()


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


def test_pressure_policy_projection_must_be_derived_from_collector_snapshot(tmp_path):
    from sentientos.host_resource_governor import evaluate_host_resource_pressure
    from sentientos.host_resource_policy import (
        build_host_resource_proposal_receipts,
        evaluate_host_resource_policy,
    )

    plan = build_observation_plan(specs=[
        HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
            lambda observed_at=None: _result("cpu", utilization_percent=20.0)),
        HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
            lambda observed_at=None: _result("memory", used_percent=40.0)),
        HostObservationCollectorSpec("disk", True, ("linux", "unknown"), 3,
            lambda observed_at=None: _result("disk", used_percent=30.0,
                free_bytes=1000)),
        HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 4,
            lambda observed_at=None: _result("nvidia_gpu", device_count=1,
                devices=[{"index": 0, "gpu_utilization_percent": 95.0,
                    "vram_utilization_percent": 92.0}]))])
    evaluation = HostResourceRuntimeCoordinator(
        kernel=ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
            phase=LifecyclePhase.RUNTIME),
        runtime_state_root=tmp_path, plan=plan).run_cycle(
            correlation_id="derived-pressure-report")
    assert evaluation is not None and validate_evaluation(evaluation).ok

    forged_pressure = evaluate_host_resource_pressure(
        evaluation.snapshot, gpu_pressure_percent=100.0)
    forged_policy = evaluate_host_resource_policy(forged_pressure)
    forged_receipts = build_host_resource_proposal_receipts(
        forged_policy, created_at=evaluation.epoch.observed_at)
    substituted = replace(evaluation, pressure_report=forged_pressure,
        policy_decision=forged_policy, proposal_receipts=forged_receipts)

    validation = validate_evaluation(substituted)
    assert not validation.ok
    assert "host_resource_pressure_report_not_derived_from_snapshot" in (
        validation.findings)

    shifted_epoch = replace(evaluation.epoch,
        observed_at="2099-01-01T00:00:00+00:00")
    shifted_timestamp = replace(evaluation, epoch=shifted_epoch)
    timestamp_validation = validate_evaluation(shifted_timestamp)
    assert not timestamp_validation.ok
    assert "observation_epoch_semantic_identity_mismatch" in (
        timestamp_validation.findings)


def test_nvml_gpu_thermal_pressure_reaches_verified_game_inference_admission(
        monkeypatch, tmp_path):
    """GPU temperature remains actionable when WSL host thermal zones are absent."""
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.0")
    kernel = ControlPlaneKernel(
        runtime_governor=RuntimeGovernor(), phase=LifecyclePhase.MAINTENANCE,
        decisions_path=tmp_path / "kernel.jsonl")

    def observe(correlation_id: str, temperature_c: float):
        plan = build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                lambda observed_at=None: _result("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                lambda observed_at=None: _result("memory", used_percent=40.0)),
            HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
                lambda observed_at=None: _result("nvidia_gpu", device_count=1,
                    sample_scope="device_wide", per_process_attribution_available=False,
                    devices=[{"index": 0, "gpu_utilization_percent": 20.0,
                              "vram_utilization_percent": 25.0,
                              "temperature_c": temperature_c}])),
            HostObservationCollectorSpec("thermal_sensors", False,
                ("linux", "unknown"), 4, lambda observed_at=None: HostCollectorResult(
                    "thermal_sensors", "unavailable", observed_at or
                    "2026-11-13T00:00:00+00:00", "test:unavailable",
                    warnings=("sensor_unavailable:thermal",))),
        ])
        evaluation = HostResourceRuntimeCoordinator(
            kernel=kernel, runtime_state_root=tmp_path / correlation_id,
            plan=plan).run_cycle(correlation_id=correlation_id)
        assert evaluation is not None and validate_evaluation(evaluation).ok
        return evaluation

    hot_game_sample = VerifiedGamePerformanceObservation(
        "windows-edge", "edge-generation-1", 1, "d" * 64, "e" * 64,
        datetime.now(timezone.utc).isoformat(), "f" * 64, 16.7, 0, 20.0,
        4096, "available")
    assert kernel.observe_verified_game_performance(hot_game_sample)
    hot = observe("gpu-thermal-hot", 90.0)
    assert hot.snapshot.gpu_utilization_percent == 20.0
    assert hot.snapshot.vram_utilization_percent == 25.0
    assert hot.snapshot.thermal_zone_temperatures_c == {"nvidia_gpu_0": 90.0}
    assert "thermal_pressure" in hot.pressure_report.pressure_labels
    assert "sensor_unavailable" in hot.pressure_report.pressure_labels

    kernel.set_phase(LifecyclePhase.RUNTIME)
    hot_decision = kernel.admit(ControlActionRequest(
        action_kind="local_model_inference",
        authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE,
        actor="user", target_subsystem="local_model",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"purpose": "local_user_chat", "correlation_id": "game-chat-hot-gpu"},
    ))
    assert hot_decision.outcome == AdmissionOutcome.DEFER
    assert "runtime_governor:deferred_local_model_inference_under_host_pressure_during_game" in hot_decision.reason_codes
    hot_evidence = hot_decision.delegated_outcomes["runtime_governor"]["evidence_refs"]
    assert hot_evidence["host_resource_evidence"]["evaluation_id"] == hot.evaluation_id
    assert hot_evidence["host_pressure_during_verified_game"] is True

    nominal_game_sample = VerifiedGamePerformanceObservation(
        "windows-edge", "edge-generation-1", 2, "a" * 64, "b" * 64,
        datetime.now(timezone.utc).isoformat(), "c" * 64, 16.7, 0, 20.0,
        4096, "available")
    assert kernel.observe_verified_game_performance(nominal_game_sample)
    kernel.set_phase(LifecyclePhase.MAINTENANCE)
    nominal = observe("gpu-thermal-nominal", 75.0)
    assert "thermal_pressure" not in nominal.pressure_report.pressure_labels
    kernel.set_phase(LifecyclePhase.RUNTIME)
    nominal_decision = kernel.admit(ControlActionRequest(
        action_kind="local_model_inference",
        authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE,
        actor="user", target_subsystem="local_model",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"purpose": "local_user_chat", "correlation_id": "game-chat-nominal-gpu"},
    ))
    assert nominal_decision.outcome == AdmissionOutcome.ALLOW


def test_host_pressure_during_verified_game_defers_foreground_chat_and_recovers(
        monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.0")
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(
        runtime_governor=governor, phase=LifecyclePhase.MAINTENANCE,
        decisions_path=tmp_path / "kernel.jsonl")

    def resource_plan(gpu: float):
        return build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                lambda observed_at=None: _result("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                lambda observed_at=None: _result("memory", used_percent=40.0)),
            HostObservationCollectorSpec("disk", True, ("linux", "unknown"), 3,
                lambda observed_at=None: _result("disk", used_percent=30.0,
                    free_bytes=1000)),
            HostObservationCollectorSpec("nvidia_gpu", False,
                ("linux", "unknown"), 4, lambda observed_at=None: _result(
                    "nvidia_gpu", device_count=1,
                    devices=[{"index": 0, "gpu_utilization_percent": gpu,
                              "vram_utilization_percent": gpu}]))])

    game_sample = VerifiedGamePerformanceObservation(
        "windows-edge", "edge-generation-1", 1, "d" * 64, "e" * 64,
        datetime.now(timezone.utc).isoformat(), "f" * 64, 16.7, 0, 20.0,
        4096, "available")
    assert governor.observe_verified_game_performance(game_sample)

    pressured = HostResourceRuntimeCoordinator(
        kernel=kernel, runtime_state_root=tmp_path / "pressure",
        plan=resource_plan(95.0)).run_cycle(correlation_id="game-gpu-pressure")
    assert pressured is not None and validate_evaluation(pressured).ok
    assert "gpu_pressure" in pressured.pressure_report.pressure_labels
    kernel.set_phase(LifecyclePhase.RUNTIME)
    foreground = ControlActionRequest(
        action_kind="local_model_inference",
        authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE,
        actor="user", target_subsystem="local_model",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"purpose": "local_user_chat", "correlation_id": "game-chat-pressure"})
    deferred = kernel.admit(foreground)
    assert deferred.outcome == AdmissionOutcome.DEFER
    assert "runtime_governor:deferred_local_model_inference_under_host_pressure_during_game" in deferred.reason_codes
    runtime_evidence = deferred.delegated_outcomes["runtime_governor"]["evidence_refs"]
    assert runtime_evidence["host_resource_evidence"]["evaluation_id"] == pressured.evaluation_id
    assert runtime_evidence["game_performance_evidence"]["message_id"] == "d" * 64
    assert runtime_evidence["host_pressure_during_verified_game"] is True

    kernel.set_phase(LifecyclePhase.MAINTENANCE)
    nominal = HostResourceRuntimeCoordinator(
        kernel=kernel, runtime_state_root=tmp_path / "recovered",
        plan=resource_plan(20.0)).run_cycle(correlation_id="game-gpu-recovered")
    assert nominal is not None and validate_evaluation(nominal).ok
    kernel.set_phase(LifecyclePhase.RUNTIME)
    recovered = kernel.admit(foreground)
    assert recovered.outcome == AdmissionOutcome.ALLOW
    assert recovered.delegated_outcomes["runtime_governor"]["evidence_refs"][
        "host_resource_evidence"]["evaluation_id"] == nominal.evaluation_id


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
    assert evidence["gpu_telemetry_complete"] is True
    assert evidence["gpu_utilization_percent"] == 15.0
