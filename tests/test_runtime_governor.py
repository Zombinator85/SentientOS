from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import tempfile

import pytest

from sentientos.foreground_game_detection import ForegroundGameObservation
from sentientos.runtime_governor import get_runtime_governor, reset_runtime_governor
from sentientos.runtime_governor import RuntimeGovernor


def test_governor_enforce_blocks_restart_budget(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RESTART_LIMIT", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    reset_runtime_governor()
    governor = get_runtime_governor()

    first = governor.admit_restart(daemon_name="alpha", scope="local", origin="local")
    second = governor.admit_restart(daemon_name="alpha", scope="local", origin="local")

    assert first.allowed is True
    assert second.allowed is False
    assert second.reason == "restart_budget_exceeded"


def test_governor_shadow_logs_without_blocking(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "shadow")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_REPAIR_LIMIT", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.95")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.95")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.95")
    reset_runtime_governor()
    governor = get_runtime_governor()

    first = governor.admit_repair(anomaly_kind="daemon_unresponsive", subject="alpha")
    second = governor.admit_repair(anomaly_kind="daemon_unresponsive", subject="alpha")

    assert first.allowed is True
    assert second.allowed is True


def test_scheduling_window_reflects_pressure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "advisory")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_SCHEDULING_THRESHOLD", "0.5")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.2")
    reset_runtime_governor()
    governor = get_runtime_governor()

    assert governor.scheduling_window_open() is True

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "1.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "1.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "1.0")
    reset_runtime_governor()
    governor = get_runtime_governor()
    assert governor.scheduling_window_open() is False


def test_decision_reason_hash_is_stable(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.2")
    reset_runtime_governor()
    governor = get_runtime_governor()

    fixed = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
    governor.observe_pulse_event(
        {
            "timestamp": fixed,
            "source_daemon": "network",
            "event_type": "enforcement",
            "priority": "critical",
            "payload": {},
        }
    )
    decision = governor.admit_federated_control(subject="network", origin="peer-a", metadata={"event_type": "restart_request"})
    assert len(decision.reason_hash) == 64


@pytest.mark.parametrize("reason_code", [
    "gaming_mode_entered", "development_chat_shutdown", "vram_pressure_observed",
])
def test_local_model_resource_release_admits_only_explicit_safe_reasons(
    monkeypatch, tmp_path, reason_code
) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.2")
    reset_runtime_governor()
    governor = get_runtime_governor()

    metadata = {
        "purpose": "local_model_resource_release",
        "reason_code": reason_code,
        "model_identity_digest": "a" * 64,
    }
    if reason_code == "vram_pressure_observed":
        metadata["resource_observation"] = {
            "schema_version": "sentientos.gaming_vram_admission_evidence:v1",
            "admission_status": "deferred", "reason_code": "vram_pressure",
            "preload_admission_status": "deferred",
            "preload_reason_code": "preload_vram_headroom_insufficient",
            "preload_threshold_percent": 75.0,
            "vram_utilization_percent": 91.0, "release_threshold_percent": 90.0,
            "recovery_threshold_percent": 80.0, "stale_after_seconds": 30.0,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
    decision = governor.admit_action(
        "local_model_resource_release",
        "development_chat",
        "test-release",
        metadata=metadata,
    )

    assert decision.allowed is True
    assert decision.reason == "model_resource_release_fail_safe"


@pytest.mark.parametrize("observation", [
    None,
    {"schema_version": "sentientos.gaming_vram_admission_evidence:v1",
     "admission_status": "deferred", "reason_code": "vram_pressure",
     "preload_admission_status": "deferred",
     "preload_reason_code": "preload_vram_headroom_insufficient",
     "preload_threshold_percent": 75.0,
     "vram_utilization_percent": 84.9, "release_threshold_percent": 85.0,
     "recovery_threshold_percent": 80.0, "stale_after_seconds": 30.0,
     "observed_at": datetime.now(timezone.utc).isoformat()},
    {"schema_version": "sentientos.gaming_vram_admission_evidence:v1",
     "admission_status": "deferred", "reason_code": "vram_pressure",
     "preload_admission_status": "deferred",
     "preload_reason_code": "preload_vram_headroom_insufficient",
     "preload_threshold_percent": 75.0,
     "vram_utilization_percent": 90.0, "release_threshold_percent": 85.0,
     "recovery_threshold_percent": 80.0, "stale_after_seconds": 1.0,
     "observed_at": "2020-01-01T00:00:00+00:00"},
])
def test_vram_pressure_release_requires_fresh_threshold_crossing(
        monkeypatch, tmp_path, observation) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    reset_runtime_governor()
    governor = get_runtime_governor()

    decision = governor.admit_action("local_model_resource_release", "development_chat",
        "test-release", metadata={"purpose": "local_model_resource_release",
            "reason_code": "vram_pressure_observed", "model_identity_digest": "a" * 64,
            "resource_observation": observation})

    assert decision.allowed is False
    assert decision.reason == "model_resource_release_pressure_evidence_required"


def test_local_model_resource_release_rejects_unknown_reason(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    reset_runtime_governor()
    governor = get_runtime_governor()

    decision = governor.admit_action(
        "local_model_resource_release",
        "development_chat",
        "test-release",
        metadata={
            "purpose": "local_model_resource_release",
            "reason_code": "arbitrary_reason",
            "model_identity_digest": "a" * 64,
        },
    )

    assert decision.allowed is False
    assert decision.reason == "model_resource_release_request_invalid"


@pytest.mark.parametrize("mutation", [
    "report_digest", "game_message_id", "pressure_labels", "below_pressure_threshold",
    "stale_observation", "wrong_target",
])
def test_production_game_gpu_release_requires_exact_current_evidence(
        monkeypatch, tmp_path, mutation):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    governor = RuntimeGovernor()
    actor = "production_chat_game_resource_governor"
    source_correlation = "production-release-evidence-source"
    observation_id = "local-chat-inference-" + hashlib.sha256(
        source_correlation.encode("utf-8")).hexdigest()[:32]
    release_correlation = "production-chat-resource-release-" + hashlib.sha256(
        source_correlation.encode("utf-8")).hexdigest()[:24]
    observed_at = datetime.now(timezone.utc).isoformat()
    game_message_id = "b" * 64
    governor._host_resource_evidence_by_correlation[observation_id] = {
        "observation_correlation_id": observation_id,
        "observed_at": observed_at,
        "report_id": "host-report-1",
        "report_digest": "c" * 64,
        "pressure_labels": ("gpu_pressure",),
        "gpu_utilization_percent": 95.0,
        "vram_utilization_percent": 93.0,
    }
    workload = ForegroundGameObservation("available", True, "a" * 64,
        observed_at, transport_provenance={"message_id": game_message_id,
            "source_id": "windows-foreground", "session_id": "session-1",
            "generation_id": "generation-1", "sequence": 1,
            "envelope_created_at": observed_at})
    assert governor.observe_verified_game_workload(workload)
    evidence = {
        "schema_version": "sentientos.production_game_gpu_resource_release_evidence:v1",
        "source_inference_correlation_id": source_correlation,
        "observation_correlation_id": observation_id,
        "host_report_id": "host-report-1",
        "host_report_digest": "c" * 64,
        "observed_at": observed_at,
        "pressure_labels": ["gpu_pressure"],
        "gpu_utilization_percent": 95.0,
        "vram_utilization_percent": 93.0,
        "game_workload_message_id": game_message_id,
    }
    metadata = {
        "purpose": "local_model_resource_release",
        "reason_code": "verified_game_gpu_pressure",
        "target_subsystem": "production_chat",
        "model_identity_digest": "d" * 64,
        "resource_observation": evidence,
    }
    if mutation == "report_digest":
        evidence["host_report_digest"] = "e" * 64
    elif mutation == "game_message_id":
        evidence["game_workload_message_id"] = "f" * 64
    elif mutation == "pressure_labels":
        evidence["pressure_labels"] = ["cpu_pressure"]
    elif mutation == "below_pressure_threshold":
        evidence["gpu_utilization_percent"] = 89.0
        evidence["vram_utilization_percent"] = 89.0
    elif mutation == "stale_observation":
        evidence["observed_at"] = "2020-01-01T00:00:00+00:00"
    elif mutation == "wrong_target":
        metadata["target_subsystem"] = "host"

    decision = governor._admit_local_model_resource_release(
        actor=actor, subject=actor, correlation_id=release_correlation,
        metadata=metadata)

    assert decision.allowed is False
    assert decision.reason == "model_resource_release_pressure_evidence_required"


@pytest.mark.parametrize("mutation", [
    "report_digest", "game_message_id", "pressure_labels", "stale_observation",
    "wrong_target", "wrong_correlation",
])
@pytest.mark.no_legacy_skip
def test_production_game_host_pressure_release_requires_exact_current_evidence(
        monkeypatch, tmp_path, mutation):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    governor = RuntimeGovernor()
    actor = "production_chat_game_resource_governor"
    source_correlation = "production-host-pressure-release-source"
    observation_id = "local-chat-inference-" + hashlib.sha256(
        source_correlation.encode("utf-8")).hexdigest()[:32]
    release_correlation = "production-chat-resource-release-" + hashlib.sha256(
        source_correlation.encode("utf-8")).hexdigest()[:24]
    observed_at = datetime.now(timezone.utc).isoformat()
    game_message_id = "b" * 64
    governor._host_resource_evidence_by_correlation[observation_id] = {
        "observation_correlation_id": observation_id,
        "observed_at": observed_at,
        "report_id": "host-report-1",
        "report_digest": "c" * 64,
        "pressure_labels": ("cpu_pressure",),
    }
    workload = ForegroundGameObservation("available", True, "a" * 64,
        observed_at, transport_provenance={"message_id": game_message_id,
            "source_id": "windows-foreground", "session_id": "session-1",
            "generation_id": "generation-1", "sequence": 1,
            "envelope_created_at": observed_at})
    assert governor.observe_verified_game_workload(workload)
    evidence = {
        "schema_version": "sentientos.production_game_host_resource_release_evidence:v1",
        "trigger_kind": "deferred_inference",
        "trigger_correlation_id": source_correlation,
        "observation_correlation_id": observation_id,
        "host_report_id": "host-report-1",
        "host_report_digest": "c" * 64,
        "observed_at": observed_at,
        "pressure_labels": ["cpu_pressure"],
        "game_workload_message_id": game_message_id,
    }
    metadata = {
        "purpose": "local_model_resource_release",
        "reason_code": "verified_game_host_pressure",
        "target_subsystem": "production_chat",
        "model_identity_digest": "d" * 64,
        "resource_observation": evidence,
    }
    if mutation == "report_digest":
        evidence["host_report_digest"] = "e" * 64
    elif mutation == "game_message_id":
        evidence["game_workload_message_id"] = "f" * 64
    elif mutation == "pressure_labels":
        evidence["pressure_labels"] = ["sensor_unavailable"]
    elif mutation == "stale_observation":
        evidence["observed_at"] = "2020-01-01T00:00:00+00:00"
    elif mutation == "wrong_target":
        metadata["target_subsystem"] = "host"

    decision = governor._admit_local_model_resource_release(
        actor=actor, subject=actor,
        correlation_id=(release_correlation + "-bad" if mutation == "wrong_correlation"
            else release_correlation), metadata=metadata)

    assert decision.allowed is False
    assert decision.reason == "model_resource_release_pressure_evidence_required"


@pytest.mark.parametrize("mutation,expected", [
    ("none", True), ("wrong_game", False), ("stale", False),
    ("no_active_game", False),
    ("zero_gpu_layers", False), ("empty_session", False),
])
@pytest.mark.no_legacy_skip
def test_verified_game_gpu_residency_release_requires_exact_fresh_game_evidence(
        monkeypatch, tmp_path, mutation, expected):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    governor = RuntimeGovernor()
    observed_at = datetime.now(timezone.utc).isoformat()
    game_message_id = "b" * 64
    observation = ForegroundGameObservation("available",
        mutation != "no_active_game", "a" * 64, observed_at,
        transport_provenance={"message_id": game_message_id, "source_id": "windows-edge",
            "session_id": "game-session", "generation_id": "edge-generation",
            "sequence": 1, "envelope_created_at": observed_at})
    assert governor.observe_verified_game_workload(observation)
    trigger = "idle-game-gpu-residency-test"
    evidence = {"schema_version": "sentientos.production_game_gpu_residency_release_evidence:v1",
        "trigger_kind": "idle_game_gpu_residency", "trigger_correlation_id": trigger,
        "game_workload_message_id": game_message_id, "model_gpu_layers": 24,
        "serving_session_id": "serving-session-1", "observed_at": observed_at}
    if mutation == "wrong_game":
        evidence["game_workload_message_id"] = "c" * 64
    elif mutation == "stale":
        evidence["observed_at"] = "2020-01-01T00:00:00+00:00"
    elif mutation == "zero_gpu_layers":
        evidence["model_gpu_layers"] = 0
    elif mutation == "empty_session":
        evidence["serving_session_id"] = ""
    release_correlation = "production-chat-resource-release-" + hashlib.sha256(
        ("idle_game_gpu_residency:" + trigger).encode("utf-8")).hexdigest()[:24]
    decision = governor._admit_local_model_resource_release(
        actor="production_chat_game_resource_governor",
        subject="production_chat_game_resource_governor",
        correlation_id=release_correlation,
        metadata={"purpose": "local_model_resource_release",
            "reason_code": "verified_game_gpu_model_residency",
            "target_subsystem": "production_chat", "model_identity_digest": "d" * 64,
            "resource_observation": evidence})
    assert decision.allowed is expected


def test_active_verified_game_defers_gpu_inference_when_gpu_telemetry_is_missing(
        monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    governor = RuntimeGovernor()
    stamp = datetime.now(timezone.utc).isoformat()
    observation = ForegroundGameObservation(
        "available", True, "a" * 64, stamp,
        transport_provenance={"message_id": "b" * 64, "source_id": "windows-edge",
            "session_id": "game-session", "generation_id": "edge-generation",
            "sequence": 1, "envelope_created_at": stamp})
    assert governor.observe_verified_game_workload(observation)
    governor._host_resource_evidence = {
        "observed_at": stamp, "evaluation_id": "evaluation-1", "epoch_id": "epoch-1",
        "snapshot_id": "snapshot-1", "report_id": "report-1",
        "report_digest": "c" * 64, "pressure_labels": (),
        "cpu_utilization_percent": 20.0, "ram_utilization_percent": 40.0,
        "gpu_utilization_percent": None, "vram_utilization_percent": None,
        "gpu_telemetry_available": False,
        "observation_correlation_id": "local-chat-inference-"
            + hashlib.sha256(b"game-no-gpu-sensor").hexdigest()[:32],
    }

    decision = governor._admit_local_model_inference(
        actor="chat_service", subject="chat", correlation_id="game-no-gpu-sensor",
        metadata={"purpose": "local_user_chat", "model_execution_profile": {
            "schema_version": "sentientos.model_execution_profile:v1",
            "engine": "llama_cpp", "accelerator_route": "gpu", "gpu_layers": 1,
            "configuration_digest": "d" * 64,
        }})

    assert decision.allowed is False
    assert decision.reason == "deferred_resource_telemetry_incomplete_during_game"
    assert decision.evidence_refs["game_workload_evidence"]["game_active"] is True


def test_federated_control_blocked_by_critical_storm(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CRITICAL_LIMIT", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.2")
    reset_runtime_governor()
    governor = get_runtime_governor()

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "network",
        "event_type": "critical_alarm",
        "priority": "critical",
        "payload": {},
    }
    governor.observe_pulse_event(event)
    governor.observe_pulse_event(event)

    decision = governor.admit_federated_control(subject="network", origin="peer-a")
    assert decision.allowed is False
    assert decision.reason == "critical_event_storm_detected"


def test_storm_reason_parity_across_restart_repair_and_federated(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CRITICAL_LIMIT", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.95")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.95")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.95")
    reset_runtime_governor()
    governor = get_runtime_governor()

    critical = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "network",
        "event_type": "critical_alarm",
        "priority": "critical",
        "payload": {},
    }
    governor.observe_pulse_event(critical)
    governor.observe_pulse_event(critical)

    restart = governor.admit_action("restart_daemon", "local", "corr-restart", metadata={"subject": "alpha"})
    repair = governor.admit_action(
        "repair_action",
        "codex_healer",
        "corr-repair",
        metadata={"subject": "alpha", "anomaly_kind": "daemon_unresponsive"},
    )
    federated = governor.admit_action(
        "federated_control",
        "peer-a",
        "corr-fed",
        metadata={"subject": "alpha", "scope": "federated"},
    )

    assert restart.reason == "critical_event_storm_detected"
    assert repair.reason == "critical_event_storm_detected"
    assert federated.reason == "critical_event_storm_detected"


def test_admit_action_routes_control_plane_task(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_TASK_LIMIT", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    reset_runtime_governor()
    governor = get_runtime_governor()

    first = governor.admit_action(
        "control_plane_task",
        "operator",
        "corr-1",
        metadata={"subject": "TASK_EXECUTION"},
    )
    second = governor.admit_action(
        "control_plane_task",
        "operator",
        "corr-2",
        metadata={"subject": "TASK_EXECUTION"},
    )

    assert first.allowed is True
    assert second.allowed is False
    assert second.reason == "control_plane_task_rate_exceeded"


def test_contention_reserves_capacity_for_recovery(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CONTENTION_LIMIT", "4")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RECOVERY_RESERVED_SLOTS", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_TASK_LIMIT", "32")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_AMENDMENT_LIMIT", "32")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    reset_runtime_governor()
    governor = get_runtime_governor()

    allowed_task = governor.admit_action("control_plane_task", "operator", "corr-task", metadata={"subject": "x"})
    denied_amendment = governor.admit_action("amendment_apply", "operator", "corr-amend", metadata={"subject": "policy"})
    recovery = governor.admit_action("repair_action", "codex_healer", "corr-repair", metadata={"subject": "alpha", "anomaly_kind": "hang"})

    assert allowed_task.allowed is True
    assert denied_amendment.allowed is False
    assert denied_amendment.reason == "deferred_reserved_for_recovery"
    assert recovery.allowed is True


def test_federated_deferred_under_pressure_local_repair_allowed(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_PRESSURE_BLOCK", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_PRESSURE_WARN", "0.7")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.9")
    reset_runtime_governor()
    governor = get_runtime_governor()

    federated = governor.admit_action(
        "federated_control",
        "peer-a",
        "corr-fed",
        metadata={"subject": "integrity", "scope": "federated"},
    )
    repair = governor.admit_action(
        "repair_action",
        "codex_healer",
        "corr-local",
        metadata={"subject": "integrity", "anomaly_kind": "signature"},
    )

    assert federated.allowed is False
    assert federated.reason == "deferred_federated_under_storm"
    assert repair.allowed is True
    assert repair.reason == "allowed_recovery_precedence"


def test_low_priority_burst_deferred_at_warn_pressure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_WARN_LOW_PRIORITY_LIMIT", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_TASK_LIMIT", "64")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_PRESSURE_BLOCK", "0.95")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_PRESSURE_WARN", "0.7")
    reset_runtime_governor()
    governor = get_runtime_governor()

    first = governor.admit_action("control_plane_task", "operator", "corr-1", metadata={"subject": "t1"})
    second = governor.admit_action("control_plane_task", "operator", "corr-2", metadata={"subject": "t2"})
    third = governor.admit_action("control_plane_task", "operator", "corr-3", metadata={"subject": "t3"})

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.reason == "deferred_low_priority_under_pressure"


def test_decision_contains_arbitration_metadata(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CONTENTION_LIMIT", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RECOVERY_RESERVED_SLOTS", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    reset_runtime_governor()
    governor = get_runtime_governor()

    governor.admit_action("control_plane_task", "operator", "corr-1", metadata={"subject": "t1"})
    denied = governor.admit_action("amendment_apply", "operator", "corr-2", metadata={"subject": "law"})

    assert denied.allowed is False
    assert denied.action_priority == 4
    assert denied.action_family == "amendment"

    decisions = (tmp_path / "governor" / "decisions.jsonl").read_text(encoding="utf-8").strip().splitlines()
    latest = decisions[-1]
    assert '"correlation_id": "corr-2"' in latest
    assert '"decision": "deny"' in latest
    assert '"governor_mode": "enforce"' in latest
    assert '"pressure_snapshot"' in latest
    assert '"action_priority": 4' in latest
    assert '"action_family": "amendment"' in latest


def test_arbitration_is_deterministic_for_same_sequence(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor-a"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CONTENTION_LIMIT", "3")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RECOVERY_RESERVED_SLOTS", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    reset_runtime_governor()
    gov_a = get_runtime_governor()
    reasons_a = [
        gov_a.admit_action("control_plane_task", "operator", "a-1", metadata={"subject": "t1"}).reason,
        gov_a.admit_action("control_plane_task", "operator", "a-2", metadata={"subject": "t2"}).reason,
        gov_a.admit_action("amendment_apply", "operator", "a-3", metadata={"subject": "law"}).reason,
        gov_a.admit_action("repair_action", "codex_healer", "a-4", metadata={"subject": "alpha", "anomaly_kind": "hang"}).reason,
    ]

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor-b"))
    reset_runtime_governor()
    gov_b = get_runtime_governor()
    reasons_b = [
        gov_b.admit_action("control_plane_task", "operator", "b-1", metadata={"subject": "t1"}).reason,
        gov_b.admit_action("control_plane_task", "operator", "b-2", metadata={"subject": "t2"}).reason,
        gov_b.admit_action("amendment_apply", "operator", "b-3", metadata={"subject": "law"}).reason,
        gov_b.admit_action("repair_action", "codex_healer", "b-4", metadata={"subject": "alpha", "anomaly_kind": "hang"}).reason,
    ]

    assert reasons_a == reasons_b


def test_observability_snapshot_contains_contention_reserved_and_starvation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CONTENTION_LIMIT", "3")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RECOVERY_RESERVED_SLOTS", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_STARVATION_STREAK_THRESHOLD", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    reset_runtime_governor()
    governor = get_runtime_governor()

    governor.admit_action("control_plane_task", "operator", "corr-1", metadata={"subject": "t1"})
    denied = governor.admit_action("amendment_apply", "operator", "corr-2", metadata={"subject": "law"})

    assert denied.allowed is False

    decision_lines = (tmp_path / "governor" / "decisions.jsonl").read_text(encoding="utf-8").strip().splitlines()
    latest = decision_lines[-1]
    assert '"contention_snapshot"' in latest
    assert '"reserved_capacity"' in latest
    assert '"starvation_signals"' in latest
    assert '"decision_outcome": "defer"' in latest

    obs_lines = (tmp_path / "governor" / "observability.jsonl").read_text(encoding="utf-8").strip().splitlines()
    obs_latest = obs_lines[-1]
    assert '"contention_snapshot"' in obs_latest
    assert '"reserved_capacity"' in obs_latest
    assert '"class_decision_summary"' in obs_latest


def test_rollup_counts_actions_storm_and_reserved_usage(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CONTENTION_LIMIT", "4")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RECOVERY_RESERVED_SLOTS", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_WARN_LOW_PRIORITY_LIMIT", "8")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_STORM_FEDERATED_LIMIT", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_PRESSURE_BLOCK", "0.95")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_PRESSURE_WARN", "0.7")
    reset_runtime_governor()
    governor = get_runtime_governor()

    governor.admit_action("federated_control", "peer-a", "corr-fed-1", metadata={"subject": "n1"})
    denied_federated = governor.admit_action("federated_control", "peer-a", "corr-fed-2", metadata={"subject": "n2"})
    governor.admit_action("control_plane_task", "operator", "corr-task", metadata={"subject": "t"})
    denied_amendment = governor.admit_action("amendment_apply", "operator", "corr-amend", metadata={"subject": "law"})
    recovery = governor.admit_action(
        "repair_action", "codex_healer", "corr-repair", metadata={"subject": "alpha", "anomaly_kind": "hang"}
    )

    assert denied_federated.reason == "deferred_federated_under_storm"
    assert denied_amendment.reason == "deferred_reserved_for_recovery"
    assert recovery.allowed is True

    import json

    rollup = json.loads((tmp_path / "governor" / "rollup.json").read_text(encoding="utf-8"))
    assert rollup["totals"]["actions"] == 5
    assert rollup["totals"]["admit"] == 3
    assert rollup["totals"]["defer"] == 2
    assert rollup["totals"]["deny"] == 0
    assert rollup["storm_trigger_counts"]["deferred_federated_under_storm"] == 1
    assert rollup["reserved_recovery_slots_used"] >= 1
    assert rollup["pressure_band_distribution"]["warn"] == 5


def test_starvation_indicator_tracks_denied_streak(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CONTENTION_LIMIT", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RECOVERY_RESERVED_SLOTS", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_STARVATION_STREAK_THRESHOLD", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    reset_runtime_governor()
    governor = get_runtime_governor()

    governor.admit_action("control_plane_task", "operator", "corr-1", metadata={"subject": "seed"})
    first_denied = governor.admit_action("amendment_apply", "operator", "corr-2", metadata={"subject": "law1"})
    second_denied = governor.admit_action("amendment_apply", "operator", "corr-3", metadata={"subject": "law2"})

    assert first_denied.allowed is False
    assert second_denied.allowed is False

    import json

    rollup = json.loads((tmp_path / "governor" / "rollup.json").read_text(encoding="utf-8"))
    starvation = rollup["starvation_signals"]
    assert starvation["denied_streaks"]["amendment_apply"] == 2
    assert "amendment_apply" in starvation["at_risk_classes"]


def test_contention_snapshot_generation_is_deterministic(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CONTENTION_LIMIT", "3")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RECOVERY_RESERVED_SLOTS", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor-a"))
    reset_runtime_governor()
    gov_a = get_runtime_governor()
    d1a = gov_a.admit_action("control_plane_task", "operator", "a-1", metadata={"subject": "t1"})
    d2a = gov_a.admit_action("amendment_apply", "operator", "a-2", metadata={"subject": "law"})

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor-b"))
    reset_runtime_governor()
    gov_b = get_runtime_governor()
    d1b = gov_b.admit_action("control_plane_task", "operator", "b-1", metadata={"subject": "t1"})
    d2b = gov_b.admit_action("amendment_apply", "operator", "b-2", metadata={"subject": "law"})

    assert d1a.reason == d1b.reason
    assert d2a.reason == d2b.reason

    import json

    obs_a = [json.loads(line) for line in (tmp_path / "governor-a" / "observability.jsonl").read_text(encoding="utf-8").splitlines()]
    obs_b = [json.loads(line) for line in (tmp_path / "governor-b" / "observability.jsonl").read_text(encoding="utf-8").splitlines()]

    keys = ["action_class", "decision_outcome", "reason", "pressure_band", "contention_snapshot", "reserved_capacity"]
    projection_a = [{k: row[k] for k in keys} for row in obs_a]
    projection_b = [{k: row[k] for k in keys} for row in obs_b]
    assert projection_a == projection_b


def test_subject_starvation_detection_with_peer_admissions(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RESTART_LIMIT", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_STARVATION_STREAK_THRESHOLD", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    reset_runtime_governor()
    governor = get_runtime_governor()

    governor.admit_action("restart_daemon", "operator", "corr-a-1", metadata={"daemon_name": "alpha", "scope": "local"})
    denied_alpha_1 = governor.admit_action("restart_daemon", "operator", "corr-a-2", metadata={"daemon_name": "alpha", "scope": "local"})
    governor.admit_action("restart_daemon", "operator", "corr-b-1", metadata={"daemon_name": "beta", "scope": "local"})
    denied_alpha_2 = governor.admit_action("restart_daemon", "operator", "corr-a-3", metadata={"daemon_name": "alpha", "scope": "local"})

    assert denied_alpha_1.allowed is False
    assert denied_alpha_2.allowed is False

    import json

    rollup = json.loads((tmp_path / "governor" / "rollup.json").read_text(encoding="utf-8"))
    starved = rollup["subject_fairness"]["starved_subjects"]
    assert any(row["action_class"] == "restart_daemon" and row["subject"] == "alpha" for row in starved)
    denied_with_peers = rollup["subject_fairness"]["denied_while_peers_admitted"]
    assert any(row["action_class"] == "restart_daemon" and row["subject"] == "alpha" for row in denied_with_peers)


def test_noisy_subject_share_is_reported(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_NOISY_SUBJECT_MIN_ADMITS", "3")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_NOISY_SUBJECT_SHARE", "0.7")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    reset_runtime_governor()
    governor = get_runtime_governor()

    governor.admit_action("control_plane_task", "operator", "corr-a-1", metadata={"task_key": "task:alpha"})
    governor.admit_action("control_plane_task", "operator", "corr-a-2", metadata={"task_key": "task:alpha"})
    governor.admit_action("control_plane_task", "operator", "corr-a-3", metadata={"task_key": "task:alpha"})
    governor.admit_action("control_plane_task", "operator", "corr-b-1", metadata={"task_key": "task:beta"})

    import json

    rollup = json.loads((tmp_path / "governor" / "rollup.json").read_text(encoding="utf-8"))
    noisy_subjects = rollup["subject_fairness"]["noisy_subjects"]
    assert any(row["action_class"] == "control_plane_task" and row["subject"] == "task:alpha" for row in noisy_subjects)


def test_queue_pressure_accounting_and_bounded_subject_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RESTART_LIMIT", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CONTENTION_LIMIT", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RECOVERY_RESERVED_SLOTS", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_SUBJECT_SUMMARY_LIMIT", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    reset_runtime_governor()
    governor = get_runtime_governor()

    governor.admit_action("control_plane_task", "operator", "corr-c-1", metadata={"task_key": "task:1"})
    governor.admit_action("amendment_apply", "operator", "corr-am-1", metadata={"amendment_target": "law:1"})
    governor.admit_action("amendment_apply", "operator", "corr-am-2", metadata={"amendment_target": "law:1"})

    governor.admit_action("restart_daemon", "operator", "corr-r-1", metadata={"daemon_name": "daemon:1", "scope": "local"})
    governor.admit_action("restart_daemon", "operator", "corr-r-2", metadata={"daemon_name": "daemon:1", "scope": "local"})

    governor.admit_action("control_plane_task", "operator", "corr-c-2", metadata={"task_key": "task:2"})
    governor.admit_action("control_plane_task", "operator", "corr-c-3", metadata={"task_key": "task:3"})
    governor.admit_action("control_plane_task", "operator", "corr-c-4", metadata={"task_key": "task:4"})

    import json

    rollup = json.loads((tmp_path / "governor" / "rollup.json").read_text(encoding="utf-8"))
    queue = rollup["queue_pressure"]
    restart_queue = queue["class_summary"]["restart_daemon"]
    assert restart_queue["admitted_occupancy"] == 1
    assert restart_queue["blocked_pressure"] == 1
    assert restart_queue["deny"] == 1

    control_queue = queue["class_summary"]["control_plane_task"]
    assert control_queue["admitted_occupancy"] >= 1
    assert control_queue["retries"] >= 1

    per_class = rollup["subject_fairness"]["per_class"]
    if "control_plane_task" in per_class:
        assert len(per_class["control_plane_task"]["subjects"]) <= 2
    assert len(rollup["queue_pressure"]["top_subjects"]) <= 2


def test_subject_fairness_projection_is_deterministic(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CONTENTION_LIMIT", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RECOVERY_RESERVED_SLOTS", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_STARVATION_STREAK_THRESHOLD", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_NOISY_SUBJECT_MIN_ADMITS", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_NOISY_SUBJECT_SHARE", "0.5")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor-a"))
    reset_runtime_governor()
    gov_a = get_runtime_governor()
    gov_a.admit_action("control_plane_task", "operator", "a-1", metadata={"task_key": "task:alpha"})
    gov_a.admit_action("control_plane_task", "operator", "a-2", metadata={"task_key": "task:alpha"})
    gov_a.admit_action("control_plane_task", "operator", "a-3", metadata={"task_key": "task:beta"})
    gov_a.admit_action("amendment_apply", "operator", "a-4", metadata={"amendment_target": "law:1"})
    gov_a.admit_action("amendment_apply", "operator", "a-5", metadata={"amendment_target": "law:1"})

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor-b"))
    reset_runtime_governor()
    gov_b = get_runtime_governor()
    gov_b.admit_action("control_plane_task", "operator", "b-1", metadata={"task_key": "task:alpha"})
    gov_b.admit_action("control_plane_task", "operator", "b-2", metadata={"task_key": "task:alpha"})
    gov_b.admit_action("control_plane_task", "operator", "b-3", metadata={"task_key": "task:beta"})
    gov_b.admit_action("amendment_apply", "operator", "b-4", metadata={"amendment_target": "law:1"})
    gov_b.admit_action("amendment_apply", "operator", "b-5", metadata={"amendment_target": "law:1"})

    import json

    rollup_a = json.loads((tmp_path / "governor-a" / "rollup.json").read_text(encoding="utf-8"))
    rollup_b = json.loads((tmp_path / "governor-b" / "rollup.json").read_text(encoding="utf-8"))

    assert rollup_a["subject_fairness"] == rollup_b["subject_fairness"]
    assert rollup_a["queue_pressure"] == rollup_b["queue_pressure"]


def test_runtime_posture_includes_reason_chain_and_dominant_cause(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_PRESSURE_BLOCK", "0.95")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_PRESSURE_WARN", "0.7")
    reset_runtime_governor()
    governor = get_runtime_governor()

    governor.admit_action("federated_control", "peer-a", "corr-fed-1", metadata={"subject": "node-1"})
    denied = governor.admit_action("federated_control", "peer-a", "corr-fed-2", metadata={"subject": "node-2"})
    assert denied.reason in {"deferred_federated_under_storm", "deferred_for_local_safety_under_pressure"}

    import json

    decisions = [
        json.loads(line)
        for line in (tmp_path / "governor" / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    payload = decisions[-1]
    posture = payload["runtime_posture"]
    assert isinstance(posture["reason_chain"], list)
    assert posture["dominant_reason"] == payload["reason"]
    assert payload["dominant_restriction_cause"] == posture["dominant_reason"]


def test_local_safety_precedence_under_mixed_posture(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "1.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "1.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "1.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_PRESSURE_BLOCK", "0.8")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_PRESSURE_WARN", "0.6")
    reset_runtime_governor()
    governor = get_runtime_governor()

    decision = governor.admit_action(
        "federated_control", "peer-a", "corr-fed", metadata={"subject": "node", "scope": "federated"}
    )
    assert decision.allowed is False
    assert decision.reason == "deferred_for_local_safety_under_pressure"


def test_pressure_and_fairness_deterministic_outcome(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CONTENTION_LIMIT", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RECOVERY_RESERVED_SLOTS", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_STARVATION_STREAK_THRESHOLD", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_PRESSURE_BLOCK", "0.95")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_PRESSURE_WARN", "0.7")
    reset_runtime_governor()
    governor = get_runtime_governor()

    governor.admit_action("control_plane_task", "operator", "corr-1", metadata={"task_key": "task:1"})
    first = governor.admit_action("amendment_apply", "operator", "corr-2", metadata={"amendment_target": "law:1"})
    second = governor.admit_action("amendment_apply", "operator", "corr-3", metadata={"amendment_target": "law:1"})

    assert first.allowed is False
    assert second.allowed is False
    assert first.reason == second.reason



@pytest.mark.no_legacy_skip
def test_pytest_harness_isolates_default_governor_storage() -> None:
    root = Path(os.environ["SENTIENTOS_GOVERNOR_ROOT"]).resolve()

    assert root != Path("/glow/governor")
    assert root.is_relative_to(Path(tempfile.gettempdir()).resolve())
