from __future__ import annotations

from pathlib import Path

from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.production_chat_resource_observation import ProductionChatResourceObservationOwner
from sentientos.production_chat_resource_provisioning_bundle_producer import (
    produce_production_chat_resource_provisioning_bundle,
)
from sentientosd import RuntimeMaintenanceSurfaces
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
