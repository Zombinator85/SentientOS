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
    from sentientos.local_model_authority import digest_payload
    from sentientos.local_runtime_provisioning import semantic_digest
    from sentientos.host_resource_policy import (
        HostResourcePolicyDecision, host_resource_policy_decision_digest,
    )

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
    loaded_identity = {"model_id": "synthetic-recovery-model", "revision": "r1"}
    loaded_identity_digest = digest_payload(loaded_identity)
    identity = InstallationIdentity.parse("production")
    registry = InstallationStateRegistry(tmp_path / "state", _test_only=True)
    bundle = handle
    release_body = {
        "schema_version": "sentientos.production_chat_resource_release_receipt:v6",
        "status": "worker_closed",
        "trigger_kind": "idle_game_gpu_residency",
        "trigger_correlation_id": "game-workload-observation",
        "release_correlation_id": "release-correlation",
        "serving_session_id": "session-1",
        "serving_operation_id": "serve-1",
        "model_identity_digest": "sha256:" + loaded_identity_digest,
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
                    "resource_release_target": {
                        "schema_version": "sentientos.production_chat_resource_release_target:v1",
                        "serving_session_id": "session-1",
                        "model_identity_digest": loaded_identity_digest},
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
                "status": "available", "source": "synthetic_test_fixture",
                "sample_scope": "device_wide",
                "per_process_attribution_available": False}]},
        "worker_exit_observed": True,
        "active_inference_preemption_requested": True,
        "active_inference_cancellation_confirmed": True,
        "active_inference_request_reference": {
            "request_id": "lmreq-" + "c" * 24,
            "request_digest": "c" * 64,
            "correlation_id": "invocation-correlation",
        },
        "resource_measurement_comparison": {
            "status": "comparable",
            "before": {"host_report_id": "host-before",
                "host_report_digest": "c" * 64,
                "observed_at": "2026-09-21T08:30:00Z",
                "gpu_utilization_percent": 74.0,
                "ram_utilization_percent": 68.0,
                "gpu_telemetry_sources": [{"collector_id": "nvidia_gpu",
                    "status": "available", "source": "synthetic_test_fixture",
                    "sample_scope": "device_wide",
                    "per_process_attribution_available": False}]},
            "after": {"host_report_id": "host-after",
                "host_report_digest": "d" * 64,
                "observed_at": "2026-09-21T08:30:05Z",
                "gpu_utilization_percent": 20.0,
                "ram_utilization_percent": 51.0,
                "gpu_telemetry_sources": [{"collector_id": "nvidia_gpu",
                    "status": "available", "source": "synthetic_test_fixture",
                    "sample_scope": "device_wide",
                    "per_process_attribution_available": False}]},
            "ram_utilization_delta_percentage_points": -17.0,
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
        "session_id": "session-1",
        "binding": {"installation_identity": str(identity),
            "serving_operation_id": "serve-1",
            "observed_loaded_model_identity": loaded_identity},
    }
    serving_receipt["receipt_id"] = "serving-receipt-" + semantic_digest(
        serving_receipt)[:24]
    serving_receipt["receipt_semantic_digest"] = semantic_digest(serving_receipt)
    serving_history = ({
        "status": "serving_receipt_verified",
        "receipt": serving_receipt,
        "receipt_semantic_digest": serving_receipt["receipt_semantic_digest"],
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

    forged_target_release = dict(release_body)
    target_record = dict(release_body["release_admission_record"])
    target_delegated = dict(target_record["delegated_outcomes"])
    target_governor = dict(target_delegated["runtime_governor"])
    target_refs = dict(target_governor["evidence_refs"])
    target_refs["resource_release_target"] = {
        **target_refs["resource_release_target"],
        "serving_session_id": "serving-session-" + "f" * 24}
    target_governor["evidence_refs"] = target_refs
    target_delegated["runtime_governor"] = target_governor
    target_record["delegated_outcomes"] = target_delegated
    forged_target_release["release_admission_record"] = target_record
    forged_target_release.pop("receipt_id")
    forged_target_release.pop("receipt_semantic_digest")
    forged_target_id = "serving-resource-release-" + hashlib.sha256(json.dumps(
        forged_target_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()[:24]
    forged_target_release["receipt_id"] = forged_target_id
    forged_target_release["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
        forged_target_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    forged_target_path = release_directory.child(forged_target_id + ".json")
    handle.durable_create(forged_target_path,
        (json.dumps(forged_target_release, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    with pytest.raises(ProductionChatResourceObservationError,
            match="resource_release_target_binding_invalid"):
        observer.observe()
    forged_target_path.path.unlink()

    forged_model_target_release = dict(release_body)
    model_target_record = dict(release_body["release_admission_record"])
    model_target_delegated = dict(model_target_record["delegated_outcomes"])
    model_target_governor = dict(model_target_delegated["runtime_governor"])
    model_target_refs = dict(model_target_governor["evidence_refs"])
    model_target_refs["resource_release_target"] = {
        **model_target_refs["resource_release_target"],
        "model_identity_digest": "2" * 64}
    model_target_governor["evidence_refs"] = model_target_refs
    model_target_delegated["runtime_governor"] = model_target_governor
    model_target_record["delegated_outcomes"] = model_target_delegated
    forged_model_target_release["release_admission_record"] = model_target_record
    forged_model_target_release["model_identity_digest"] = "sha256:" + "2" * 64
    forged_model_target_release.pop("receipt_id")
    forged_model_target_release.pop("receipt_semantic_digest")
    forged_model_target_id = "serving-resource-release-" + hashlib.sha256(json.dumps(
        forged_model_target_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()[:24]
    forged_model_target_release["receipt_id"] = forged_model_target_id
    forged_model_target_release["receipt_semantic_digest"] = hashlib.sha256(
        json.dumps(forged_model_target_release, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    forged_model_target_path = release_directory.child(
        forged_model_target_id + ".json")
    handle.durable_create(forged_model_target_path,
        (json.dumps(forged_model_target_release, sort_keys=True,
            separators=(",", ":"), ensure_ascii=False,
            allow_nan=False) + "\n").encode("utf-8"))
    with pytest.raises(ProductionChatResourceObservationError,
            match="resource_release_target_binding_invalid"):
        observer.observe()
    forged_model_target_path.path.unlink()

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

    host_evidence_release = dict(release_body)
    host_evidence_release["resource_observation"] = {
        **release_body["resource_observation"],
        "observation_correlation_id": "host-observation-correlation",
        "host_report_id": "host-report-1",
        "host_report_digest": "a" * 64,
        "pressure_labels": ["gpu_pressure"],
        "game_workload_message_id": "b" * 64,
        "gpu_utilization_percent": 22.0,
        "vram_utilization_percent": 86.0,
        "host_telemetry_used_for_admission": True,
    }
    policy_decision = HostResourcePolicyDecision(
        decision_id="host-policy-decision-1", report_id="host-report-1",
        report_digest="a" * 64)
    host_policy_binding = {
        "schema_version": "sentientos.host_resource_policy_admission_binding:v1",
        "policy_decision_id": policy_decision.decision_id,
        "policy_decision_status": policy_decision.status,
        "policy_decision_digest": host_resource_policy_decision_digest(
            policy_decision),
        "policy_proposal_only": True,
        "policy_decision": policy_decision.to_dict(),
    }
    host_evidence_release["resource_observation"][
        "host_policy_binding"] = host_policy_binding
    host_evidence_record = dict(release_body["release_admission_record"])
    host_evidence_delegated = dict(host_evidence_record["delegated_outcomes"])
    host_evidence_governor = dict(host_evidence_delegated["runtime_governor"])
    host_evidence_refs = dict(host_evidence_governor["evidence_refs"])
    host_evidence_refs["resource_observation_evidence"] = {
        "status": "current",
        "schema_version": (
            "sentientos.production_game_host_resource_release_evidence:v2"),
        "observation_correlation_id": "host-observation-correlation",
        "host_report_id": "host-report-1",
        "host_report_digest": "a" * 64,
        "pressure_labels": ["gpu_pressure"],
        "game_workload_message_id": "b" * 64,
        "gpu_utilization_percent": 22.0,
        "vram_utilization_percent": 86.0,
        "active_inference_preemption_requested": True,
        "host_policy_binding": host_policy_binding,
    }
    host_evidence_governor["evidence_refs"] = host_evidence_refs
    host_evidence_delegated["runtime_governor"] = host_evidence_governor
    host_evidence_record["delegated_outcomes"] = host_evidence_delegated
    host_evidence_release["release_admission_record"] = host_evidence_record
    host_evidence_release["resource_observation"]["gpu_utilization_percent"] = 22.0
    verified_host_release = dict(host_evidence_release)
    verified_host_release.pop("receipt_id")
    verified_host_release.pop("receipt_semantic_digest")
    verified_host_id = "serving-resource-release-" + hashlib.sha256(json.dumps(
        verified_host_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()[:24]
    verified_host_release["receipt_id"] = verified_host_id
    verified_host_release["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
        verified_host_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    verified_host_path = release_directory.child(verified_host_id + ".json")
    handle.durable_create(verified_host_path, (json.dumps(
        verified_host_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    try:
        verified_snapshot = observer.observe()
        verified_projection = next(item for item in
            verified_snapshot.verified_resource_release_receipts
            if item.get("receipt_id") == verified_host_id)
        assert verified_projection["host_measurement_binding_posture"] == "verified"
        assert verified_projection["resource_observation"][
            "host_policy_binding"]["policy_decision_id"] == (
                policy_decision.decision_id)
    finally:
        verified_host_path.path.unlink()

    tampered_policy_release = json.loads(json.dumps(host_evidence_release))
    tampered_policy_release["resource_observation"]["host_policy_binding"][
        "policy_decision_digest"] = "0" * 64
    tampered_policy_release.pop("receipt_id")
    tampered_policy_release.pop("receipt_semantic_digest")
    tampered_policy_id = "serving-resource-release-" + hashlib.sha256(json.dumps(
        tampered_policy_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()[:24]
    tampered_policy_release["receipt_id"] = tampered_policy_id
    tampered_policy_release["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
        tampered_policy_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    tampered_policy_path = release_directory.child(tampered_policy_id + ".json")
    handle.durable_create(tampered_policy_path, (json.dumps(
        tampered_policy_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    with pytest.raises(ProductionChatResourceObservationError,
            match="resource_release_host_policy_binding_mismatch"):
        observer.observe()
    tampered_policy_path.path.unlink()

    host_evidence_release["resource_observation"]["gpu_utilization_percent"] = 23.0
    host_evidence_release.pop("receipt_id")
    host_evidence_release.pop("receipt_semantic_digest")
    host_evidence_id = "serving-resource-release-" + hashlib.sha256(json.dumps(
        host_evidence_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()[:24]
    host_evidence_release["receipt_id"] = host_evidence_id
    host_evidence_release["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
        host_evidence_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    host_evidence_path = release_directory.child(host_evidence_id + ".json")
    handle.durable_create(host_evidence_path,
        (json.dumps(host_evidence_release, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    with pytest.raises(ProductionChatResourceObservationError,
            match="resource_release_host_observation_admission_mismatch"):
        observer.observe()
    host_evidence_path.path.unlink()

    for release_kind, measurements, labels in (
            ("gpu", {"gpu_utilization_percent": 94.0,
                "vram_utilization_percent": 92.0}, ["gpu_pressure"]),
            ("memory", {"ram_utilization_percent": 94.0}, ["memory_pressure"])):
        general_release = json.loads(json.dumps(host_evidence_release))
        general_observation = general_release["resource_observation"]
        general_observation.pop("game_workload_message_id")
        general_observation.pop("gpu_utilization_percent", None)
        general_observation.pop("vram_utilization_percent", None)
        general_observation.update({
            "pressure_labels": labels,
            "active_inference_preemption_requested": False,
            "host_telemetry_used_for_admission": True,
            **measurements,
        })
        general_release["active_inference_preemption_requested"] = False
        general_release["active_inference_cancellation_confirmed"] = False
        general_evidence = {
            "status": "current",
            "observation_correlation_id": "host-observation-correlation",
            "host_report_id": "host-report-1",
            "host_report_digest": "a" * 64,
            "pressure_labels": labels,
            "active_inference_preemption_requested": False,
            "host_policy_binding": host_policy_binding,
            **measurements,
        }
        general_record = general_release["release_admission_record"]
        general_record["delegated_outcomes"]["runtime_governor"][
            "evidence_refs"]["resource_observation_evidence"] = general_evidence
        general_release.pop("receipt_id")
        general_release.pop("receipt_semantic_digest")
        general_id = "serving-resource-release-" + hashlib.sha256(json.dumps(
            general_release, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()[:24]
        general_release["receipt_id"] = general_id
        general_release["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
            general_release, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
        general_path = release_directory.child(general_id + ".json")
        handle.durable_create(general_path, (json.dumps(
            general_release, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
        try:
            general_snapshot = observer.observe()
            general_projection = next(item for item in
                general_snapshot.verified_resource_release_receipts
                if item.get("receipt_id") == general_id)
            assert general_projection["host_measurement_binding_posture"] == "verified"
        finally:
            general_path.path.unlink()

    legacy_host_release = dict(host_evidence_release)
    legacy_host_release["schema_version"] = (
        "sentientos.production_chat_resource_release_receipt:v5")
    legacy_host_release["resource_observation"] = {
        **host_evidence_release["resource_observation"],
        "gpu_utilization_percent": 22.0}
    legacy_record = dict(host_evidence_record)
    legacy_delegated = dict(host_evidence_delegated)
    legacy_governor = dict(host_evidence_governor)
    legacy_refs = dict(host_evidence_refs)
    legacy_refs.pop("resource_release_target")
    legacy_resource_evidence = dict(
        host_evidence_refs["resource_observation_evidence"])
    legacy_resource_evidence.pop("schema_version")
    legacy_resource_evidence.pop("gpu_utilization_percent")
    legacy_resource_evidence.pop("vram_utilization_percent")
    legacy_refs["resource_observation_evidence"] = legacy_resource_evidence
    legacy_governor["evidence_refs"] = legacy_refs
    legacy_delegated["runtime_governor"] = legacy_governor
    legacy_record["delegated_outcomes"] = legacy_delegated
    legacy_host_release["release_admission_record"] = legacy_record
    legacy_host_release.pop("receipt_id")
    legacy_host_release.pop("receipt_semantic_digest")
    legacy_id = "serving-resource-release-" + hashlib.sha256(json.dumps(
        legacy_host_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()[:24]
    legacy_host_release["receipt_id"] = legacy_id
    legacy_host_release["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
        legacy_host_release, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    legacy_path = release_directory.child(legacy_id + ".json")
    handle.durable_create(legacy_path,
        (json.dumps(legacy_host_release, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    try:
        legacy_snapshot = observer.observe()
        legacy_projected = next(item for item in
            legacy_snapshot.verified_resource_release_receipts
            if item.get("receipt_id") == legacy_id)
        assert legacy_projected["host_measurement_binding_posture"] == (
            "legacy_report_bound_measurements_unbound")
        from sentientos.host_resource_runtime import (
            resource_consumption_world_state_records,
        )
        legacy_world_state = resource_consumption_world_state_records(
            ledger=legacy_snapshot.ledger,
            verified_resource_release_receipts=(
                legacy_snapshot.verified_resource_release_receipts))[0]
        assert any(item.get("host_measurement_binding_posture") ==
            "legacy_report_bound_measurements_unbound"
            for item in legacy_world_state["payload"]["resource_release_receipts"])
    finally:
        legacy_path.path.unlink()

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
        "serving_receipt_semantic_digest"] == serving_receipt["receipt_semantic_digest"]
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
        "source": "synthetic_test_fixture", "sample_scope": "device_wide",
        "per_process_attribution_available": False},)
    comparison = projected_release["resource_measurement_comparison"]
    assert comparison["before"]["gpu_utilization_percent"] == 74.0
    assert comparison["before"]["ram_utilization_percent"] == 68.0
    assert comparison["after"]["ram_utilization_percent"] == 51.0
    assert comparison["ram_utilization_delta_percentage_points"] == -17.0
    assert comparison["before"]["gpu_telemetry_sources"] == ({
        "collector_id": "nvidia_gpu", "status": "available",
        "source": "synthetic_test_fixture", "sample_scope": "device_wide",
        "per_process_attribution_available": False},)
    assert comparison["after"]["gpu_telemetry_sources"] == ({
        "collector_id": "nvidia_gpu", "status": "available",
        "source": "synthetic_test_fixture", "sample_scope": "device_wide",
        "per_process_attribution_available": False},)
    assert comparison["after"]["report_id"] == "host-after"
    assert comparison["before"]["report_digest"] == "c" * 64
    assert comparison["after"]["report_digest"] == "d" * 64
    assert comparison["interpretation"] == (
        "sample_delta_only; telemetry_does_not_establish_causation")
    assert projected["disposition"] == "degraded"
    assert projected["payload"]["resource_release_receipt_posture"] == "degraded"
    projection_serving_receipt = dict(serving_receipt)
    projection_history_body = {
        "status": "legacy_receipt_without_reservation", "attempt": None,
        "attempt_semantic_digest": None, "receipt": projection_serving_receipt,
        "receipt_semantic_digest": serving_receipt["receipt_semantic_digest"],
    }
    projection_serving_history = ({**projection_history_body,
        "history_semantic_digest": semantic_digest(projection_history_body)},)
    serving_link_projection = resource_consumption_world_state_records(
        ledger=first.ledger,
        source_identity={"installation_identity": str(identity)},
        verified_serving_operation_history=projection_serving_history,
        verified_resource_release_receipts=first.verified_resource_release_receipts)[0]
    assert not any(item.startswith(
        "resource_release_serving_model_linkage_missing_or_mismatched:")
        for item in serving_link_projection["payload"]["lineage_findings"])
    wrapper_only_forgery = dict(projection_serving_receipt)
    wrapper_only_forgery_binding = dict(wrapper_only_forgery["binding"])
    wrapper_only_forgery_binding["observed_loaded_model_identity"] = {
        "model_id": "wrapper-only-forgery", "revision": "r1"}
    wrapper_only_forgery["binding"] = wrapper_only_forgery_binding
    wrapper_only_forgery_body = {**projection_history_body,
        "receipt": wrapper_only_forgery}
    wrapper_only_forgery_history = ({**wrapper_only_forgery_body,
        "history_semantic_digest": semantic_digest(wrapper_only_forgery_body)},)
    with pytest.raises(ValueError,
            match="serving_operation_history_receipt_identity_invalid"):
        resource_consumption_world_state_records(
            ledger=first.ledger,
            source_identity={"installation_identity": str(identity)},
            verified_serving_operation_history=wrapper_only_forgery_history,
            verified_resource_release_receipts=first.verified_resource_release_receipts)
    conflicting_serving_receipt = dict(projection_serving_receipt)
    conflicting_serving_receipt["receipt_id"] = "serving-receipt-" + "f" * 24
    conflicting_binding = dict(conflicting_serving_receipt["binding"])
    conflicting_binding["observed_loaded_model_identity"] = {
        "model_id": "different-synthetic-model", "revision": "r1"}
    conflicting_serving_receipt["binding"] = conflicting_binding
    conflicting_serving_receipt.pop("receipt_id")
    conflicting_serving_receipt.pop("receipt_semantic_digest")
    conflicting_serving_receipt["receipt_id"] = "serving-receipt-" + semantic_digest(
        conflicting_serving_receipt)[:24]
    conflicting_serving_receipt["receipt_semantic_digest"] = semantic_digest(
        conflicting_serving_receipt)
    conflicting_history_body = {**projection_history_body,
        "receipt": conflicting_serving_receipt,
        "receipt_semantic_digest": conflicting_serving_receipt[
            "receipt_semantic_digest"]}
    conflicting_serving_history = (*projection_serving_history, {
        **conflicting_history_body,
        "history_semantic_digest": semantic_digest(conflicting_history_body)})
    with pytest.raises(ValueError,
            match="resource_release_serving_history_collision"):
        resource_consumption_world_state_records(
            ledger=first.ledger,
            source_identity={"installation_identity": str(identity)},
            verified_serving_operation_history=conflicting_serving_history,
            verified_resource_release_receipts=first.verified_resource_release_receipts)
    duplicate_history_projection = resource_consumption_world_state_records(
        ledger=first.ledger,
        source_identity={"installation_identity": str(identity)},
        verified_serving_operation_history=(
            *projection_serving_history, projection_serving_history[0]),
        verified_resource_release_receipts=first.verified_resource_release_receipts)[0]
    assert not any(item.startswith(
        "resource_release_serving_model_linkage_missing_or_mismatched:")
        for item in duplicate_history_projection["payload"]["lineage_findings"])
    tampered_release = dict(first.verified_resource_release_receipts[0])
    tampered_release["status"] = "denied"
    with pytest.raises(ValueError,
            match="resource_release_receipt_digest_mismatch"):
        resource_consumption_world_state_records(
            ledger=first.ledger,
            verified_resource_release_receipts=(tampered_release,))

    forged_release = dict(first.verified_resource_release_receipts[0])
    forged_admission = dict(forged_release["release_admission_record"])
    forged_delegated = dict(forged_admission["delegated_outcomes"])
    forged_governor = dict(forged_delegated["runtime_governor"])
    forged_evidence = dict(forged_governor["evidence_refs"])
    forged_target = dict(forged_evidence["resource_release_target"])
    forged_target["model_identity_digest"] = "e" * 64
    forged_evidence["resource_release_target"] = forged_target
    forged_governor["evidence_refs"] = forged_evidence
    forged_delegated["runtime_governor"] = forged_governor
    forged_admission["delegated_outcomes"] = forged_delegated
    forged_release["release_admission_record"] = forged_admission
    forged_release["model_identity_digest"] = "e" * 64
    enriched_fields = {
        "serving_receipt_linkage_posture", "serving_receipt_id",
        "serving_receipt_semantic_digest", "invocation_linkage_posture",
        "cancelled_invocation_receipt_id", "cancelled_invocation_receipt_digest",
        "cancelled_invocation_preemption_ref", "host_measurement_binding_posture",
    }
    forged_body = {key: value for key, value in forged_release.items()
        if key not in enriched_fields and key != "receipt_semantic_digest"}
    forged_identity_body = dict(forged_body)
    forged_identity_body.pop("receipt_id", None)
    forged_release["receipt_id"] = "serving-resource-release-" + hashlib.sha256(
        json.dumps(forged_identity_body, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()[:24]
    forged_body["receipt_id"] = forged_release["receipt_id"]
    forged_release["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
        forged_body, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    forged_projection = resource_consumption_world_state_records(
        ledger=first.ledger,
        source_identity={"installation_identity": str(identity)},
        verified_serving_operation_history=projection_serving_history,
        verified_resource_release_receipts=(forged_release,))[0]
    assert any(item.startswith(
        "resource_release_serving_model_linkage_missing_or_mismatched:")
        for item in forged_projection["payload"]["lineage_findings"])
    assert forged_projection["payload"]["resource_release_receipt_posture"] == "degraded"

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
    projected_v10_release = v10_linked_projection["payload"][
        "resource_release_receipts"][0]
    assert "cancelled_invocation_preemption_ref" not in projected_v10_release
    assert any("resource_release_invocation_linkage_missing_or_mismatched:" in item
        for item in v10_linked_projection["payload"]["lineage_findings"])
    forged_v10_release = {
        **v10_linked_releases[0],
        "cancelled_invocation_preemption_ref": {
            **preemption_ref, "preemption_evidence_digest": "f" * 64},
    }
    forged_v10_projection = resource_consumption_world_state_records(
        ledger=first.ledger,
        invocation_receipts=(),
        verified_resource_release_receipts=(forged_v10_release,))[0]
    assert "cancelled_invocation_preemption_ref" not in forged_v10_projection[
        "payload"]["resource_release_receipts"][0]
    assert any("resource_release_invocation_linkage_missing_or_mismatched:" in item
        for item in forged_v10_projection["payload"]["lineage_findings"])
    monkeypatch.setattr(
        "sentientos.governed_local_model_invocation.validate_receipt",
        lambda _receipt: (True, ()))
    corroborated_v10_release = {
        **v10_linked_releases[0],
        "cancelled_invocation_receipt_id": exact_linked_v10["receipt_id"],
        "cancelled_invocation_receipt_digest": exact_linked_v10["receipt_digest"],
        "cancelled_invocation_preemption_ref": preemption_ref,
    }
    corroborated_v10_projection = resource_consumption_world_state_records(
        ledger=first.ledger,
        invocation_receipts=(exact_linked_v10,),
        verified_resource_release_receipts=(corroborated_v10_release,))[0]
    assert corroborated_v10_projection["payload"]["resource_release_receipts"][0][
        "cancelled_invocation_preemption_ref"] == preemption_ref
    assert not any("resource_release_preemption_linkage_missing_or_mismatched:" in item
        for item in corroborated_v10_projection["payload"]["lineage_findings"])
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
        summarize_gpu_telemetry_source,
    )
    from sentientos.production_chat_resource_provisioning import (
        load_production_chat_resource_context_owner,
    )
    from sentientos.host_resource_policy import host_resource_policy_decision_digest
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
                collector("nvidia_gpu", sample_scope="device_wide",
                    per_process_attribution_available=False,
                    device_count=1, devices=[{
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
        "policy_decision_id": evaluation.policy_decision.decision_id,
        "policy_decision_status": evaluation.policy_decision.status,
        "policy_decision_digest": host_resource_policy_decision_digest(
            evaluation.policy_decision),
        "policy_decision": evaluation.policy_decision.to_dict(),
        "policy_proposal_only": evaluation.policy_decision.proposal_only,
        "semantic_digest": evaluation.semantic_digest,
        "observed_at": evaluation.epoch.observed_at,
        "pressure_labels": list(evaluation.pressure_report.pressure_labels),
        "thermal_zone_temperatures_c": dict(
            evaluation.snapshot.thermal_zone_temperatures_c),
        "cpu_utilization_percent": evaluation.snapshot.cpu_utilization_percent,
        "ram_utilization_percent": evaluation.snapshot.ram_utilization_percent,
        "gpu_utilization_percent": evaluation.snapshot.gpu_utilization_percent,
        "vram_utilization_percent": evaluation.snapshot.vram_utilization_percent,
        "gpu_telemetry_sources": [summarize_gpu_telemetry_source(result)
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
        assert host_binding["policy_decision_id"] == host_observation[
            "policy_decision_id"]
        assert host_binding["policy_decision_status"] == host_observation[
            "policy_decision_status"]
        assert host_binding["policy_decision_digest"] == host_observation[
            "policy_decision_digest"]
        assert host_binding["policy_decision"]["decision_id"] == (
            evaluation.policy_decision.decision_id)
        assert host_binding["policy_decision"]["proposal_only"] is True
        assert host_binding["policy_proposal_only"] is True
        assert host_binding["schema_version"] == (
            "sentientos.resource_admission_host_observation_binding:v4")
        assert host_binding["gpu_telemetry_sources"] == ({
            "collector_id": "nvidia_gpu", "status": "available",
            "source": "synthetic_test_fixture", "sample_scope": "device_wide",
            "per_process_attribution_available": False},)
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

        tampered_policy_decision = json.loads(decision_bytes)
        tampered_policy_decision["delegated_outcomes"]["runtime_governor"][
            "evidence_refs"]["host_resource_evidence"][
                "policy_decision_digest"] = "0" * 64
        handle.durable_replace(decision_file,
            (json.dumps(tampered_policy_decision, sort_keys=True,
                separators=(",", ":"), ensure_ascii=False, allow_nan=False)
                + "\n").encode("utf-8"))
        with pytest.raises(ProductionChatResourceObservationError,
                match="resource_inference_host_observation_binding_mismatch"):
            observer.observe()
        handle.durable_replace(decision_file, decision_bytes)

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
