"""Restart and corruption controls for immutable resource observation custody."""
from __future__ import annotations

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
