"""Restart and corruption controls for immutable resource observation custody."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.production_chat_resource_provisioning import load_production_chat_resource_context_owner
from sentientos.production_chat_resource_observation import (
    ProductionChatResourceObservationError,
    ProductionChatResourceObservationOwner,
)
from sentientos.production_chat_resource_provisioning_bundle_producer import (
    produce_production_chat_resource_provisioning_bundle,
)
from tests.test_production_chat_resource_provisioning_bundle_producer import inputs

pytestmark = pytest.mark.no_legacy_skip


def test_reconstruction_is_read_only_stable_and_does_not_replenish(
        tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    handle, values = inputs(tmp_path, calls=3)
    published = produce_production_chat_resource_provisioning_bundle(handle, "recovery", **values)
    writer = load_production_chat_resource_context_owner(
        handle, "recovery", clock=lambda: "2026-09-21T08:30:00Z",
        nonce_source=lambda: "consumed-once")
    writer.allocator.final_gate(
        allocation=writer.allocation, principal=writer.principal,
        authenticated=writer.authenticated, current=writer.current, policy=writer.policy,
        current_time="2026-09-21T08:30:00Z", durable_attempt_nonce="consumed-once")
    writer.close()
    identity = InstallationIdentity.parse("production")
    registry = InstallationStateRegistry(tmp_path / "state", _test_only=True)
    bundle = handle
    release_body = {
        "schema_version": "sentientos.production_chat_resource_release_receipt:v5",
        "status": "worker_closed",
        "trigger_kind": "idle_game_gpu_residency",
        "trigger_correlation_id": "game-workload-observation",
        "release_correlation_id": "release-correlation",
        "serving_session_id": "session-1",
        "serving_operation_id": "serve-1",
        "model_identity_digest": "sha256:" + "1" * 64,
        "release_admission_decision_ref": "kernel_decision:release-correlation",
        "release_admission_outcome": "allow",
        "release_admission_witness": {
            "schema_version": "sentientos.resource_release_admission_witness:v1",
            "outcome": "allow", "reason_codes": [], "current_phase": "runtime",
            "requested_phase": "runtime",
            "authority_class": "local_model_resource_release",
            "action_kind": "local_model_resource_release",
            "actor": "production_chat_game_resource_governor",
            "target_subsystem": "production_chat",
            "correlation_id": "release-correlation",
            "admission_decision_ref": "kernel_decision:release-correlation",
        },
        "release_admission_record": {
            "event_type": "control_plane_decision",
            "timestamp": "2026-09-21T08:30:00+00:00",
            "final_disposition": "allow", "outcome": "allow",
            "reason_codes": [], "delegate_checks_consulted": [],
            "lifecycle_phase": "runtime", "current_phase": "runtime",
            "requested_phase": "runtime",
            "authority_class": "local_model_resource_release",
            "action_kind": "local_model_resource_release",
            "actor_source": "production_chat_game_resource_governor",
            "actor": "production_chat_game_resource_governor",
            "execution_owner": "production_chat_game_resource_governor",
            "target_subsystem": "production_chat", "delegated_outcomes": {
                "runtime_governor": {"evidence_refs": {
                    "active_inference_request_reference": {
                        "request_id": "lmreq-" + "c" * 24,
                        "request_digest": "c" * 64,
                        "correlation_id": "invocation-correlation"},
                    "resource_observation_evidence": {
                        "active_inference_preemption_requested": True}}}},
            "federation_context": None, "proof_budget_context": None,
            "protected_mutation_intent": None,
            "correlation_id": "release-correlation",
            "admission_decision_ref": "kernel_decision:release-correlation",
        },
        "release_reason_codes": [],
        "resource_observation": {"workload_mode": "gaming",
            "active_inference_preemption_requested": False,
            "gpu_telemetry_available": True, "gpu_telemetry_complete": True,
            "gpu_telemetry_sources": [{"collector_id": "nvidia_gpu",
                "status": "available", "source": "synthetic_test_fixture"}]},
        "worker_exit_observed": True,
        "active_inference_preemption_requested": True,
        "active_inference_cancellation_confirmed": True,
        "active_inference_request_reference": {
            "request_id": "lmreq-" + "c" * 24,
            "request_digest": "c" * 64,
            "correlation_id": "invocation-correlation",
        },
        "resource_measurement_comparison": {
            "before": {"host_report_id": "host-before",
                "observed_at": "2026-09-21T08:30:00Z",
                "gpu_utilization_percent": 74.0,
                "gpu_telemetry_sources": [{"collector_id": "nvidia_gpu",
                    "status": "available", "source": "synthetic_test_fixture"}]},
            "after": {"host_report_id": "host-after",
                "observed_at": "2026-09-21T08:30:05Z",
                "gpu_utilization_percent": 20.0,
                "gpu_telemetry_sources": [{"collector_id": "nvidia_gpu",
                    "status": "available", "source": "synthetic_test_fixture"}]},
            "interpretation": "sample_delta_only; telemetry_does_not_establish_causation"},
        "inference_performed": False,
        "host_mutation_performed": False,
    }
    encoded_release_body = json.dumps(release_body, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    release_id = "serving-resource-release-" + hashlib.sha256(
        encoded_release_body).hexdigest()[:24]
    release_body["receipt_id"] = release_id
    release_body["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
        release_body, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    release_directory = handle.fixed_object(
        "local-model/serving/resource-release-receipts")
    handle.ensure_directory(release_directory)
    handle.durable_create(release_directory.child(release_id + ".json"),
        (json.dumps(release_body, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    ledger_path = bundle.fixed_object(
        "local-model/resource-provisioning/recovery/resource-ledger.json").path
    original = ledger_path.read_bytes()
    observer = ProductionChatResourceObservationOwner(
        registry.open_read_only(identity), "recovery")
    serving_receipt = {
        "receipt_id": "serving-receipt-" + "a" * 24,
        "session_id": "session-1",
        "binding": {"serving_operation_id": "serve-1"},
    }
    serving_history = ({
        "status": "serving_receipt_verified",
        "receipt": serving_receipt,
        "receipt_semantic_digest": "b" * 64,
    },)
    monkeypatch.setattr(
        "sentientos.production_chat_resource_observation.read_serving_operation_history",
        lambda *args, **kwargs: serving_history)

    forged_witness_release = dict(release_body)
    forged_witness_release["release_admission_witness"] = {
        **release_body["release_admission_witness"], "actor": "unowned_actor"}
    forged_identity_body = dict(forged_witness_release)
    forged_identity_body.pop("receipt_id")
    forged_identity_body.pop("receipt_semantic_digest")
    forged_body = json.dumps(forged_identity_body, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    forged_id = "serving-resource-release-" + hashlib.sha256(forged_body).hexdigest()[:24]
    forged_witness_release["receipt_id"] = forged_id
    forged_witness_release.pop("receipt_semantic_digest")
    forged_witness_release["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
        forged_witness_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    forged_path = release_directory.child(forged_id + ".json")
    handle.durable_create(forged_path,
        (json.dumps(forged_witness_release, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    with pytest.raises(ProductionChatResourceObservationError,
            match="resource_release_admission_witness_invalid"):
        observer.observe()
    forged_path.path.unlink()

    forged_record_release = dict(release_body)
    forged_record_release["release_admission_record"] = {
        **release_body["release_admission_record"], "actor": "substituted_actor"}
    forged_record_release.pop("receipt_id")
    forged_record_release.pop("receipt_semantic_digest")
    forged_record_id = "serving-resource-release-" + hashlib.sha256(json.dumps(
        forged_record_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()[:24]
    forged_record_release["receipt_id"] = forged_record_id
    forged_record_release["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
        forged_record_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    forged_record_path = release_directory.child(forged_record_id + ".json")
    handle.durable_create(forged_record_path,
        (json.dumps(forged_record_release, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    with pytest.raises(ProductionChatResourceObservationError,
            match="resource_release_admission_record_invalid"):
        observer.observe()
    forged_record_path.path.unlink()

    forged_evidence_release = dict(release_body)
    forged_evidence_record = dict(release_body["release_admission_record"])
    forged_evidence_delegated = dict(forged_evidence_record["delegated_outcomes"])
    forged_evidence_governor = dict(forged_evidence_delegated["runtime_governor"])
    forged_evidence_refs = dict(forged_evidence_governor["evidence_refs"])
    forged_evidence_refs["active_inference_request_reference"] = {
        **release_body["active_inference_request_reference"],
        "request_id": "lmreq-" + "d" * 24}
    forged_evidence_governor["evidence_refs"] = forged_evidence_refs
    forged_evidence_delegated["runtime_governor"] = forged_evidence_governor
    forged_evidence_record["delegated_outcomes"] = forged_evidence_delegated
    forged_evidence_release["release_admission_record"] = forged_evidence_record
    forged_evidence_release.pop("receipt_id")
    forged_evidence_release.pop("receipt_semantic_digest")
    forged_evidence_id = "serving-resource-release-" + hashlib.sha256(json.dumps(
        forged_evidence_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()[:24]
    forged_evidence_release["receipt_id"] = forged_evidence_id
    forged_evidence_release["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
        forged_evidence_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    forged_evidence_path = release_directory.child(forged_evidence_id + ".json")
    handle.durable_create(forged_evidence_path,
        (json.dumps(forged_evidence_release, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    with pytest.raises(ProductionChatResourceObservationError,
            match="resource_release_cancelled_invocation_admission_evidence_mismatch"):
        observer.observe()
    forged_evidence_path.path.unlink()

    first = observer.observe()
    second = observer.observe()
    unrecorded_body = dict(release_body)
    unrecorded_body["status"] = "admission_unrecorded"
    unrecorded_body["release_admission_record"] = None
    unrecorded_body.pop("receipt_id")
    unrecorded_body.pop("receipt_semantic_digest")
    unrecorded_id = "serving-resource-release-" + hashlib.sha256(json.dumps(
        unrecorded_body, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()[:24]
    unrecorded_body["receipt_id"] = unrecorded_id
    unrecorded_body["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
        unrecorded_body, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    unrecorded_path = release_directory.child(unrecorded_id + ".json")
    handle.durable_create(unrecorded_path,
        (json.dumps(unrecorded_body, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    try:
        recovered_unrecorded = observer.observe()
        assert recovered_unrecorded.resource_release_receipt_posture == (
            "admission_unrecorded")
        from sentientos.host_resource_runtime import (
            resource_consumption_world_state_records,
        )
        unrecorded_projection = resource_consumption_world_state_records(
            ledger=recovered_unrecorded.ledger,
            verified_resource_release_receipts=(
                recovered_unrecorded.verified_resource_release_receipts))[0]
        assert unrecorded_projection["payload"][
            "resource_release_receipt_posture"] == "degraded"
        assert any(item.startswith("resource_release_admission_unrecorded:")
            for item in unrecorded_projection["payload"]["lineage_findings"])
    finally:
        unrecorded_path.path.unlink()
    assert first.manifest_digest == second.manifest_digest
    first_snapshot = first.ledger.observation_snapshot()
    second_snapshot = second.ledger.observation_snapshot()
    assert first_snapshot == second_snapshot
    assert first_snapshot["ledger_digest"]
    assert len(first_snapshot["allocations"]) == 1
    assert len(first_snapshot["attempts"]) == 1
    assert first_snapshot["attempts"][0]["status"] == "provisional"
    assert first_snapshot["attempts"][0]["allocation_id"] == published.allocation_id
    assert first_snapshot["allocations"][0]["resource_specific_bounds"]["max_calls_per_correlation"] == 3
    assert len(first.verified_resource_release_receipts) == 1
    assert first.verified_resource_release_receipts[0]["receipt_id"] == release_id
    assert first.verified_resource_release_receipts[0][
        "serving_receipt_linkage_posture"] == "verified"
    assert first.verified_resource_release_receipts[0][
        "serving_receipt_semantic_digest"] == "b" * 64
    assert first.resource_release_receipt_posture == "pending_invocation_receipts"
    from sentientos.host_resource_runtime import resource_consumption_world_state_records
    projected = resource_consumption_world_state_records(
        ledger=first.ledger,
        verified_resource_release_receipts=first.verified_resource_release_receipts)[0]
    assert projected["payload"]["resource_release_receipt_count"] == 1
    projected_release = projected["payload"]["resource_release_receipts"][0]
    assert projected_release["release_admission_decision_ref"] == (
        "kernel_decision:release-correlation")
    assert projected_release["release_admission_witness"]["actor"] == (
        "production_chat_game_resource_governor")
    projected_observation = projected_release["resource_observation"]
    assert projected_observation["gpu_telemetry_available"] is True
    assert projected_observation["gpu_telemetry_complete"] is True
    assert projected_observation["gpu_telemetry_sources"] == ({
        "collector_id": "nvidia_gpu", "status": "available",
        "source": "synthetic_test_fixture"},)
    comparison = projected_release["resource_measurement_comparison"]
    assert comparison["before"]["gpu_utilization_percent"] == 74.0
    assert comparison["before"]["gpu_telemetry_sources"] == ({
        "collector_id": "nvidia_gpu", "status": "available",
        "source": "synthetic_test_fixture"},)
    assert comparison["after"]["report_id"] == "host-after"
    assert comparison["interpretation"] == (
        "sample_delta_only; telemetry_does_not_establish_causation")
    assert projected["disposition"] == "degraded"
    assert projected["payload"]["resource_release_receipt_posture"] == "degraded"
    tampered_release = dict(first.verified_resource_release_receipts[0])
    tampered_release["status"] = "denied"
    with pytest.raises(ValueError,
            match="resource_release_receipt_digest_mismatch"):
        resource_consumption_world_state_records(
            ledger=first.ledger,
            verified_resource_release_receipts=(tampered_release,))

    linked_invocation = {
        "receipt_id": "lmrec-" + "d" * 24,
        "receipt_digest": "d" * 64,
        "status": "cancelled",
        "reason_codes": ["cancelled_for_workload_transition"],
        "cancellation_admission_decision_ref": "kernel_decision:release-correlation",
        "request": {
            "request_id": "lmreq-" + "c" * 24,
            "request_digest": "c" * 64,
            "correlation_id": "invocation-correlation",
        },
    }
    linked_releases, linked_posture = observer._resource_release_receipts(
        serving_history, (linked_invocation,))
    assert linked_posture == "verified"
    assert linked_releases[0]["invocation_linkage_posture"] == "verified"
    assert linked_releases[0]["cancelled_invocation_receipt_id"] == (
        linked_invocation["receipt_id"])
    linked_projection = resource_consumption_world_state_records(
        ledger=first.ledger,
        invocation_receipts=(linked_invocation,),
        verified_resource_release_receipts=linked_releases)[0]
    # Invocation linkage does not complete the separate provisional allocator
    # attempt; recovery must continue to report the combined state degraded.
    assert linked_projection["disposition"] == "degraded"
    assert linked_projection["payload"]["recovery_posture"] == (
        "incomplete_attempts_present")
    assert linked_projection["payload"]["resource_release_receipts"][0][
        "cancelled_invocation_receipt_digest"] == linked_invocation["receipt_digest"]
    exact_linked_v7 = {
        **linked_invocation,
        "schema_version": "sentientos.local_model_invocation_receipt:v7",
        "cancellation_admission_decision_ref": (
            release_body["release_admission_decision_ref"]),
        "cancellation_admission_record": dict(
            release_body["release_admission_record"]),
    }
    legacy_linked_releases, legacy_linked_posture = observer._resource_release_receipts(
        serving_history, (exact_linked_v7,))
    assert legacy_linked_posture == "verified"
    assert legacy_linked_releases[0]["invocation_linkage_posture"] == "verified"
    exact_linked_invocation = {
        **linked_invocation,
        "schema_version": "sentientos.local_model_invocation_receipt:v8",
        "cancellation_admission_decision_ref": (
            release_body["release_admission_decision_ref"]),
        "cancellation_admission_record": dict(
            release_body["release_admission_record"]),
    }
    exact_linked_releases, exact_linked_posture = observer._resource_release_receipts(
        serving_history, (exact_linked_invocation,))
    assert exact_linked_posture == "verified"
    assert exact_linked_releases[0]["invocation_linkage_posture"] == "verified"
    preemption_ref = {
        "schema_version": "sentientos.local_model_cancellation_preemption_ref:v1",
        "cancellation_admission_decision_ref": (
            release_body["release_admission_decision_ref"]),
        "active_inference_request_reference": {
            key: linked_invocation["request"][key] for key in (
                "request_id", "request_digest", "correlation_id")},
        "preemption_evidence_kind": "runtime_governor_evidence_refs",
        "preemption_evidence_digest": "e" * 64,
    }
    exact_linked_v10 = {
        **exact_linked_invocation,
        "schema_version": "sentientos.local_model_invocation_receipt:v10",
        "effects": {"local_model_inference": True},
        "cancellation_preemption_ref": preemption_ref,
    }
    v10_linked_releases, v10_linkage_posture = observer._resource_release_receipts(
        serving_history, (exact_linked_v10,))
    assert v10_linkage_posture == "verified"
    assert v10_linked_releases[0]["cancelled_invocation_preemption_ref"] == (
        preemption_ref)
    v10_linked_projection = resource_consumption_world_state_records(
        ledger=first.ledger,
        # The fixture exercises the recovery owner's already-verified join;
        # the full typed invocation custody contract is covered by the serving
        # integration test, not synthesized again in this projection fixture.
        invocation_receipts=(),
        verified_resource_release_receipts=v10_linked_releases)[0]
    assert v10_linked_projection["payload"]["resource_release_receipts"][0][
        "cancelled_invocation_preemption_ref"] == preemption_ref
    substituted_invocation = {
        **exact_linked_invocation,
        "cancellation_admission_record": {
            **exact_linked_invocation["cancellation_admission_record"],
            "actor": "substituted_actor",
        },
    }
    with pytest.raises(ProductionChatResourceObservationError,
            match="resource_release_cancelled_invocation_admission_record_mismatch"):
        observer._resource_release_receipts(
            serving_history, (substituted_invocation,))
    serving_history = ({"status": "serving_receipt_verified",
        "receipt": {**serving_receipt, "binding": {
            "serving_operation_id": "substituted-operation"}},
        "receipt_semantic_digest": "b" * 64},)
    with pytest.raises(ProductionChatResourceObservationError,
            match="resource_release_serving_operation_linkage_invalid"):
        observer.observe()
    serving_history = ({"status": "serving_receipt_verified",
        "receipt": serving_receipt,
        "receipt_semantic_digest": "b" * 64},)
    release_path = release_directory.child(release_id + ".json").path
    original_release_bytes = release_path.read_bytes()
    corrupted_release = dict(release_body)
    corrupted_release["status"] = "denied"
    release_path.write_text(json.dumps(corrupted_release, sort_keys=True,
        separators=(",", ":")), encoding="utf-8")
    with pytest.raises(ProductionChatResourceObservationError,
            match="resource_release_receipt_binding_invalid"):
        observer.observe()
    release_path.write_bytes(original_release_bytes)
    mismatched_release = dict(release_body)
    mismatched_release.pop("receipt_id")
    mismatched_release.pop("receipt_semantic_digest")
    mismatched_release["release_admission_outcome"] = "deny"
    mismatched_body = json.dumps(mismatched_release, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    mismatched_id = "serving-resource-release-" + hashlib.sha256(
        mismatched_body).hexdigest()[:24]
    mismatched_release["receipt_id"] = mismatched_id
    mismatched_release["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
        mismatched_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    mismatched_path = release_directory.child(mismatched_id + ".json").path
    mismatched_path.write_text(json.dumps(mismatched_release, sort_keys=True,
        separators=(",", ":")), encoding="utf-8")
    try:
        with pytest.raises(ProductionChatResourceObservationError,
                match="resource_release_admission_outcome_status_mismatch"):
            observer.observe()
    finally:
        mismatched_path.unlink()
    assert ledger_path.read_bytes() == original

    reopened = ProductionChatResourceObservationOwner(
        registry.open_read_only(identity), "recovery").observe()
    assert reopened.manifest_digest == first.manifest_digest
    assert reopened.ledger.observation_snapshot() == first_snapshot
    assert ledger_path.read_bytes() == original


def test_missing_or_corrupt_durable_ledger_stays_incomplete(tmp_path: Path) -> None:
    handle, values = inputs(tmp_path, calls=1)
    produce_production_chat_resource_provisioning_bundle(handle, "recovery", **values)
    identity = InstallationIdentity.parse("production")
    registry = InstallationStateRegistry(tmp_path / "state", _test_only=True)
    bundle = handle
    ledger_path = bundle.fixed_object(
        "local-model/resource-provisioning/recovery/resource-ledger.json").path
    original = ledger_path.read_bytes()
    observer = ProductionChatResourceObservationOwner(
        registry.open_read_only(identity), "recovery")

    ledger_path.write_bytes(b"{truncated")
    with pytest.raises(ProductionChatResourceObservationError, match="resource_ledger_invalid"):
        observer.observe()
    ledger_path.unlink()
    with pytest.raises(ProductionChatResourceObservationError, match="resource_ledger_missing"):
        observer.observe()
    ledger_path.write_bytes(original)
    recovered = ProductionChatResourceObservationOwner(
        registry.open_read_only(identity), "recovery").observe()
    recovered_snapshot = recovered.ledger.observation_snapshot()
    assert len(recovered_snapshot["allocations"]) == 1
    assert recovered_snapshot["attempts"] == ()
    assert ledger_path.read_bytes() == original


def test_resource_invocation_admission_recovery_binds_exact_host_observation(
        tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from sentientos.control_plane_kernel import ControlPlaneKernel, LifecyclePhase
    from sentientos.host_collectors import HostCollectorResult
    from sentientos.host_resource_runtime import (
        HostObservationCollectorSpec, HostResourceRuntimeCoordinator,
        build_observation_plan, resource_consumption_world_state_records,
    )
    from sentientos.production_chat_resource_provisioning import (
        load_production_chat_resource_context_owner,
    )
    import sentientos.runtime_governor as runtime_governor_module
    from tests.test_governed_local_model_resource_invocation_composition import (
        setup as invocation_setup,
    )

    handle, values = inputs(tmp_path, calls=2)
    produce_production_chat_resource_provisioning_bundle(
        handle, "admission-link", **values)
    now = "2026-09-21T08:30:00Z"
    frozen_now = datetime(2026, 9, 21, 8, 30, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen_now if tz is not None else frozen_now.replace(tzinfo=None)

    monkeypatch.setattr(runtime_governor_module, "datetime", FrozenDateTime)
    kernel = ControlPlaneKernel(phase=LifecyclePhase.RUNTIME,
        decisions_path=tmp_path / "kernel-decisions.jsonl")

    def collector(collector_id: str, **metrics):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now,
            "synthetic_test_fixture", values=metrics)

    observation_owner = HostResourceRuntimeCoordinator(
        kernel=kernel, runtime_state_root=tmp_path / "host-runtime",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
            HostObservationCollectorSpec("nvidia_gpu", False,
                ("linux", "unknown"), 3,
                collector("nvidia_gpu", device_count=1, devices=[{
                    "index": 0, "gpu_utilization_percent": 15.0,
                    "vram_utilization_percent": 30.0}])),
        ]), clock=lambda: now)
    correlation_id = "resource-admission-host-observation-link"
    observation_id = "local-chat-inference-" + hashlib.sha256(
        correlation_id.encode("utf-8")).hexdigest()[:32]
    evaluation = observation_owner.run_cycle(correlation_id=observation_id)
    assert evaluation is not None
    host_observation = {
        "schema_version": "sentientos.production_chat_host_resource_observation:v1",
        "status": "current", "evaluation_id": evaluation.evaluation_id,
        "observation_correlation_id": evaluation.epoch.correlation_id,
        "epoch_id": evaluation.epoch.epoch_id,
        "snapshot_id": evaluation.snapshot.snapshot_id,
        "report_id": evaluation.pressure_report.report_id,
        "report_digest": evaluation.policy_decision.report_digest,
        "semantic_digest": evaluation.semantic_digest,
        "observed_at": evaluation.epoch.observed_at,
        "pressure_labels": list(evaluation.pressure_report.pressure_labels),
        "thermal_zone_temperatures_c": dict(
            evaluation.snapshot.thermal_zone_temperatures_c),
        "cpu_utilization_percent": evaluation.snapshot.cpu_utilization_percent,
        "ram_utilization_percent": evaluation.snapshot.ram_utilization_percent,
        "gpu_utilization_percent": evaluation.snapshot.gpu_utilization_percent,
        "vram_utilization_percent": evaluation.snapshot.vram_utilization_percent,
        "gpu_telemetry_sources": [{
            "collector_id": result.collector_id, "status": result.status,
            "source": result.source[:128]}
            for result in evaluation.epoch.results
            if result.collector_id == "nvidia_gpu"],
        "gpu_telemetry_available": (
            evaluation.snapshot.gpu_utilization_percent is not None
            or evaluation.snapshot.vram_utilization_percent is not None),
        "gpu_telemetry_complete": (
            evaluation.snapshot.gpu_utilization_percent is not None
            and evaluation.snapshot.vram_utilization_percent is not None),
        "no_effect_authority": True,
    }
    backend, invoker, base_request, _unused_context, _unused_ledger = invocation_setup(
        tmp_path / "model", kernel=kernel)
    request = invoker.build_request(purpose="local_user_chat", prompt="hello",
        caller="resource-observation-test", correlation_id=correlation_id,
        budget=base_request.budget,
        linkage={"host_resource_observation": host_observation})
    resource_owner = load_production_chat_resource_context_owner(
        handle, "admission-link", clock=lambda: now,
        nonce_source=lambda: "admission-link-attempt")
    try:
        receipt = invoker.invoke(request, resource_context=resource_owner.next_context())
        assert receipt.status == "admitted_completed", receipt.reason_codes
        assert backend.calls == 1
        decision_path = (tmp_path / "model" / "runtime" / "decisions"
            / (request.request_id + ".json"))
        decision_bytes = decision_path.read_bytes()
        receipt_directory = handle.fixed_object("local-model/inference/receipts")
        handle.ensure_directory(receipt_directory)
        handle.durable_create(receipt_directory.child(receipt.receipt_id + ".json"),
            (json.dumps(receipt.to_dict(), sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
        decision_directory = handle.fixed_object("local-model/inference/decisions")
        handle.ensure_directory(decision_directory)
        decision_file = decision_directory.child(request.request_id + ".json")
        handle.durable_create(decision_file, decision_bytes)

        identity = InstallationIdentity.parse("production")
        readonly = InstallationStateRegistry(
            tmp_path / "state", _test_only=True).open_read_only(identity)
        observer = ProductionChatResourceObservationOwner(readonly, "admission-link")
        observed = observer.observe()
        witness = observed.verified_inference_admission_decisions[0]
        assert witness["schema_version"] == (
            "sentientos.resource_bound_inference_admission_witness:v3")
        assert witness["admission_decision_record"] == (
            receipt.admission_decision_record)
        host_binding = witness["host_resource_observation_binding"]
        assert host_binding["status"] == "current"
        assert host_binding["report_digest"] == host_observation["report_digest"]
        assert host_binding["semantic_digest"] == host_observation["semantic_digest"]
        assert receipt.admission_decision_record == json.loads(decision_bytes)
        projection = resource_consumption_world_state_records(
            ledger=observed.ledger,
            invocation_receipts=observed.invocation_receipts,
            verified_inference_admission_decisions=(witness,))[0]
        projected_invocation = projection["payload"]["invocation_receipts"][0]
        assert projected_invocation["host_resource_observation_binding_posture"] == (
            "verified_current_observation")
        assert projected_invocation["host_resource_observation_admission_binding"] == (
            host_binding)
        assert projected_invocation["admission_decision_record"] == (
            receipt.admission_decision_record)

        tampered_decision = json.loads(decision_bytes)
        tampered_decision["delegated_outcomes"]["runtime_governor"][
            "evidence_refs"]["host_resource_evidence"]["report_digest"] = "0" * 64
        handle.durable_replace(decision_file,
            (json.dumps(tampered_decision, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
        with pytest.raises(ProductionChatResourceObservationError,
                match="resource_inference_host_observation_binding_mismatch"):
            observer.observe()
        handle.durable_replace(decision_file, decision_bytes)
    finally:
        resource_owner.close()
