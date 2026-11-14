"""Restart and corruption controls for immutable resource observation custody."""
from __future__ import annotations

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


def test_reconstruction_is_read_only_stable_and_does_not_replenish(tmp_path: Path) -> None:
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
        "schema_version": "sentientos.production_chat_resource_release_receipt:v2",
        "status": "worker_closed",
        "trigger_kind": "idle_game_gpu_residency",
        "trigger_correlation_id": "game-workload-observation",
        "release_correlation_id": "release-correlation",
        "serving_session_id": "session-1",
        "serving_operation_id": "serve-1",
        "model_identity_digest": "sha256:" + "1" * 64,
        "release_admission_decision_ref": "kernel_decision:release-correlation",
        "release_admission_outcome": "allow",
        "release_reason_codes": [],
        "resource_observation": {"workload_mode": "gaming",
            "active_inference_preemption_requested": False},
        "worker_exit_observed": True,
        "active_inference_preemption_requested": False,
        "active_inference_cancellation_confirmed": None,
        "resource_measurement_comparison": {
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

    first = observer.observe()
    second = observer.observe()
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
    assert first.verified_resource_release_receipts == (release_body,)
    assert first.resource_release_receipt_posture == "verified"
    from sentientos.host_resource_runtime import resource_consumption_world_state_records
    projected = resource_consumption_world_state_records(
        ledger=first.ledger,
        verified_resource_release_receipts=first.verified_resource_release_receipts)[0]
    assert projected["payload"]["resource_release_receipt_count"] == 1
    assert projected["payload"]["resource_release_receipts"][0][
        "release_admission_decision_ref"] == (
            "kernel_decision:release-correlation")
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
