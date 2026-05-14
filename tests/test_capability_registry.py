from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.capability_registry import (
    CapabilityRecord,
    CapabilityRegistry,
    build_default_capability_registry,
    capability_registry_digest,
    replace_capability_record,
    summarize_capability_registry,
    validate_capability_registry,
)

pytestmark = pytest.mark.no_legacy_skip


def test_default_registry_builds_deterministically_and_validates() -> None:
    first = build_default_capability_registry()
    second = build_default_capability_registry()
    assert capability_registry_digest(first) == capability_registry_digest(second)
    assert validate_capability_registry(first).ok
    assert first.metadata_only is True


def test_summary_shape_is_metadata_only_and_digest_changes_on_metadata() -> None:
    registry = build_default_capability_registry()
    summary = summarize_capability_registry(registry)
    assert summary["metadata_only"] is True
    assert summary["no_runtime_authority_expansion"] is True
    assert "direct_fan_pwm_thermal_control" in summary["capability_ids"]
    changed = replace_capability_record(registry, "host_resource_telemetry", status="partial")
    assert capability_registry_digest(changed) != summary["digest"]


def test_direct_fan_pwm_is_deferred_or_blocked_not_implemented() -> None:
    record = build_default_capability_registry().by_id()["direct_fan_pwm_thermal_control"]
    assert record.status in {"blocked", "deferred"}
    assert record.host_actuation_performed is False
    assert "fan/PWM writes" in record.deferred_surfaces


def test_hardware_driver_awareness_references_driver_manager() -> None:
    record = build_default_capability_registry().by_id()["hardware_driver_awareness"]
    assert record.status in {"implemented", "partial"}
    assert "sentientos/daemons/driver_manager.py" in record.source_paths
    assert "driver installation" in record.deferred_surfaces


def test_gui_and_browser_interaction_implemented_but_gated() -> None:
    records = build_default_capability_registry().by_id()
    for capability_id in ("gui_host_interaction", "browser_host_interaction"):
        record = records[capability_id]
        assert record.status == "implemented"
        assert record.authority_level == "gated_host_interaction"
        assert record.requires_control_plane_admission is True
        assert record.requires_operator_approval is True
        assert record.requires_panic_stop is True
        assert record.requires_audit_receipt is True
        assert record.host_actuation_performed is False


def test_federation_evidence_is_implemented_but_not_transport_adoption_or_sync() -> None:
    records = build_default_capability_registry().by_id()
    evidence = records["federation_evidence_custody"]
    transport = records["federation_transport_sync_adoption"]
    assert evidence.status == "implemented"
    assert evidence.authority_level == "federation_evidence"
    assert {"transport", "sync", "adoption"}.issubset(set(evidence.deferred_surfaces))
    assert transport.status in {"blocked", "deferred"}


def test_provider_invocation_remains_blocked_or_deferred() -> None:
    record = build_default_capability_registry().by_id()["provider_invocation"]
    assert record.status in {"blocked", "deferred"}
    assert record.provider_required is False
    assert record.network_required is False
    assert record.prompt_assembly_required is False
    assert "provider invocation" in record.deferred_surfaces


def test_validation_rejects_unsupported_implemented_host_actuation_without_requirements() -> None:
    registry = CapabilityRegistry(
        registry_id="bad",
        records=(
            CapabilityRecord(
                capability_id="bad_actuation",
                category="host_resource_telemetry",
                status="implemented",
                authority_level="observation",
                host_actuation_performed=True,
            ),
        ),
    )
    result = validate_capability_registry(registry)
    assert not result.ok
    assert any("host_actuation" in finding for finding in result.findings)


def test_validation_rejects_fan_pwm_implemented_claim_without_source_or_proof() -> None:
    registry = CapabilityRegistry(
        registry_id="bad",
        records=(
            CapabilityRecord(
                capability_id="bad_fan",
                category="host_resource_telemetry",
                status="implemented",
                authority_level="privileged_host_action",
                implemented_surfaces=("fan/PWM actuation",),
                host_actuation_performed=True,
                requires_control_plane_admission=True,
                requires_operator_approval=True,
                requires_panic_stop=True,
                requires_audit_receipt=True,
                requires_rollback_receipt=True,
            ),
        ),
    )
    result = validate_capability_registry(registry)
    assert not result.ok
    assert any("fan_pwm" in finding for finding in result.findings)


def test_validation_rejects_provider_network_prompt_authority_claims() -> None:
    base = build_default_capability_registry().by_id()["local_model_chat"]
    bad = replace(base, provider_required=True)
    result = validate_capability_registry(CapabilityRegistry(registry_id="bad", records=(bad,)))
    assert not result.ok
    assert any("provider_network_prompt" in finding for finding in result.findings)


def test_validation_rejects_federation_evidence_as_transport() -> None:
    bad = CapabilityRecord(
        capability_id="bad_federation",
        category="federation_evidence",
        status="implemented",
        authority_level="federation_evidence",
        implemented_surfaces=("transport and adoption",),
    )
    result = validate_capability_registry(CapabilityRegistry(registry_id="bad", records=(bad,)))
    assert not result.ok
    assert any("federation_evidence" in finding for finding in result.findings)
