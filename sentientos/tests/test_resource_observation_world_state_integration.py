from __future__ import annotations

from pathlib import Path

from sentientos.governed_local_model_invocation import LocalModelInvocationBudget
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.local_model_serving_inference import ProductionServingInferenceController
from sentientos.production_chat_resource_observation import ProductionChatResourceObservationOwner
from sentientos.production_chat_resource_provisioning_bundle_producer import (
    produce_production_chat_resource_provisioning_bundle,
)
from sentientos.production_chat_resource_provisioning import load_production_chat_resource_context_owner
from sentientosd import RuntimeMaintenanceSurfaces
from tests.test_local_model_serving_inference import setup as serving_setup
from tests.test_production_chat_resource_provisioning_bundle_producer import inputs


def test_explicit_read_only_resource_owner_reaches_runtime_world_state(
        tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path / "repo"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(tmp_path / "trust"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(tmp_path / "trust" / "state.json"))
    registry, provisioning_inputs = inputs(tmp_path)
    bundle = produce_production_chat_resource_provisioning_bundle(
        registry, "integration", **provisioning_inputs)
    ledger_path = registry.fixed_object(
        "local-model/resource-provisioning/integration/resource-ledger.json").path
    ledger_before = ledger_path.read_bytes()

    observer_handle = InstallationStateRegistry(
        tmp_path / "state", _test_only=True).open_read_only(
            InstallationIdentity.parse("production"))
    observer = ProductionChatResourceObservationOwner(observer_handle, "integration")
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path,
        resource_observation_owner=observer,
        resource_observation_configuration_status={
            "status": "configured", "read_only": True, "effect_authority": False,
        },
    )

    surfaces.build_world_state_board(tick_id="2026-09-21T08:40:00Z")

    snapshot = surfaces.current_world_state_snapshot
    assert snapshot is not None
    resource_facts = [fact for fact in snapshot.facts
        if fact.source.kind == "resource_governor"
        and fact.source.source_id == "governed_local_model_resource_consumption"]
    assert len(resource_facts) == 1, surfaces._resource_observation_health
    assert surfaces._resource_observation_health["status"] == "degraded"
    assert surfaces._resource_observation_health["effect_authority"] is False
    payload = resource_facts[0].payload
    assert payload["source_identity"]["installation_identity"] == "production"
    assert payload["source_identity"]["provisioning_id"] == "integration"
    assert payload["source_identity"]["manifest_digest"] == bundle.manifest_digest
    assert payload["allocation_count"] == 1
    assert payload["allocations"][0]["allocation_id"] == bundle.allocation_id
    assert payload["attempt_count"] == 0
    assert payload["consumption_receipt_count"] == 0
    assert payload["invocation_receipt_count"] == 0
    assert payload["shared_host_usage_attribution"] == "unknown_without_independent_observation"
    assert resource_facts[0].effect_claimed is False
    assert resource_facts[0].effect_proven is False
    assert ledger_path.read_bytes() == ledger_before


def test_owner_produced_invocation_and_debit_reach_world_state(
        tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path / "repo"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(tmp_path / "trust"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(tmp_path / "trust" / "state.json"))
    registry, provisioning_inputs = inputs(tmp_path, calls=2)
    bridge, serving, _, model, _, _ = serving_setup(
        monkeypatch, tmp_path, installation_identity="production")
    bundle = produce_production_chat_resource_provisioning_bundle(
        registry, "invocation-integration", **provisioning_inputs)
    context_owner = load_production_chat_resource_context_owner(
        registry, "invocation-integration", clock=lambda: "2026-09-21T08:30:00Z",
        nonce_source=lambda: "installed-invocation-attempt")
    try:
        receipt = bridge.generate(
            prompt="bounded local request", caller="test-operator",
            correlation_id="installed-invocation",
            budget=LocalModelInvocationBudget(100, 200, 20, 5.0, 2),
            resource_context=context_owner.next_context())
        assert receipt.status == "admitted_completed", receipt.reason_codes
        assert receipt.effects["local_model_inference"] is True
        assert model.calls == 1

        ledger_path = registry.fixed_object(
            "local-model/resource-provisioning/invocation-integration/resource-ledger.json").path
        readonly = InstallationStateRegistry(
            tmp_path / "state", _test_only=True).open_read_only(
                InstallationIdentity.parse("production"))
        observer = ProductionChatResourceObservationOwner(readonly, "invocation-integration")
        surfaces = RuntimeMaintenanceSurfaces(
            tmp_path, resource_observation_owner=observer,
            resource_observation_configuration_status={
                "status": "configured", "read_only": True, "effect_authority": False,
            })
        surfaces.build_world_state_board(tick_id="2026-09-21T08:40:00Z")

        snapshot = surfaces.current_world_state_snapshot
        assert snapshot is not None
        facts = [fact for fact in snapshot.facts
            if fact.source.kind == "resource_governor"
            and fact.source.source_id == "governed_local_model_resource_consumption"]
        assert len(facts) == 1, surfaces._resource_observation_health
        payload = facts[0].payload
        assert surfaces._resource_observation_health["status"] == "degraded"
        assert surfaces._resource_observation_health["invocation_receipt_posture"] == "verified"
        assert surfaces._resource_observation_health["chat_process_runtime_observation_posture"] == "unknown_missing"
        assert payload["source_identity"]["manifest_digest"] == bundle.manifest_digest
        assert payload["allocation_count"] == 1
        allocation = payload["allocations"][0]
        assert allocation["allocation_id"] == bundle.allocation_id
        assert allocation["allocation_digest"] == bundle.allocation_digest
        assert payload["attempt_count"] == 1
        attempt = payload["attempts"][0]
        assert attempt["allocation_id"] == bundle.allocation_id
        assert attempt["status"] == "begun"
        assert payload["consumption_receipt_count"] == 3
        consumptions = payload["consumption_receipts"]
        assert [item["state"] for item in consumptions] == [
            "attempt_begun", "measured_completed", "reconciled"]
        assert all(item["attempt_id"] == attempt["attempt_id"] for item in consumptions)
        assert all(item["allocation_digest"] == bundle.allocation_digest for item in consumptions)
        assert {item["observed_at"] for item in consumptions} == {"2026-09-21T08:30:00Z"}
        assert consumptions[-1]["effect_receipt_digest"] == receipt.receipt_digest
        assert payload["invocation_receipt_count"] == 1
        invocation = payload["invocation_receipts"][0]
        assert invocation["receipt_id"] == receipt.receipt_id
        assert invocation["receipt_digest"] == receipt.receipt_digest
        assert invocation["resource_attempt_id"] == attempt["attempt_id"]
        assert invocation["resource_consumption_receipt_digests"] == [
            item["receipt_digest"] for item in consumptions[1:]]
        assert invocation["resource_allocation_digest"] == bundle.allocation_digest
        assert payload["shared_host_usage_attribution"] == "unknown_without_independent_observation"
        assert facts[0].disposition == "recorded"
        assert facts[0].observed_at is None
        assert facts[0].source.staleness == "undated"
        assert facts[0].effect_claimed is False and facts[0].effect_proven is False
        assert context_owner.allocator.ledger.remaining_calls(bundle.allocation_id) == 1
        assert ledger_path.exists()
    finally:
        context_owner.close()
        serving.close()
