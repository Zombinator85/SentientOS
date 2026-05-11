from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from scripts.verify_context_hygiene_prompt_boundaries import scan_context_hygiene_prompt_boundaries, summarize_context_hygiene_prompt_boundary_scan
from sentientos.context_hygiene.prompt_provider_invocation_denial_attestation import ProviderInvocationDenialAttestationDecision
from sentientos.context_hygiene.prompt_provider_invocation_denial_closure import (
    ProviderInvocationDenialClosureGuardrailSummary,
    build_provider_invocation_denial_closure_manifest,
)
from sentientos.context_hygiene.prompt_provider_invocation_denial_enforcement import (
    ProviderInvocationDenialEnforcementStatus,
    build_provider_invocation_denial_enforcement_snapshot,
    compute_provider_invocation_denial_enforcement_digest,
    explain_provider_invocation_denial_enforcement_findings,
    provider_invocation_denial_enforcement_blocks_release,
    provider_invocation_denial_enforcement_contains_no_client,
    provider_invocation_denial_enforcement_contains_no_endpoint,
    provider_invocation_denial_enforcement_contains_no_export,
    provider_invocation_denial_enforcement_contains_no_network,
    provider_invocation_denial_enforcement_contains_no_prompt_text,
    provider_invocation_denial_enforcement_contains_no_provider,
    provider_invocation_denial_enforcement_contains_no_runtime_authority,
    provider_invocation_denial_enforcement_contains_no_secret,
    provider_invocation_denial_enforcement_grants_no_clearance,
    provider_invocation_denial_enforcement_grants_no_unblock,
    provider_invocation_denial_enforcement_is_metadata_only,
    provider_invocation_denial_enforcement_ready,
    summarize_provider_invocation_denial_enforcement_snapshot,
    validate_provider_invocation_denial_enforcement_snapshot,
)
from tests.test_phase99_provider_invocation_denial_attestation import _attestation

MODULE_PATH = Path("sentientos/context_hygiene/prompt_provider_invocation_denial_enforcement.py")
PROMPT_ASSEMBLER_PATH = Path("prompt_assembler.py")


def _guardrail() -> ProviderInvocationDenialClosureGuardrailSummary:
    return ProviderInvocationDenialClosureGuardrailSummary(
        prompt_boundary_guardrail_clean=True,
        architecture_boundaries_clean=True,
        import_purity_clean=True,
        immutability_audit_clean=True,
        guardrail_summary_complete=True,
    )


def _arch(**overrides):
    data = {
        "architecture_boundaries_clean": True,
        "clean": True,
        "contradictory": False,
        "provider_invocation_allowed": False,
        "runtime_authority_allowed": False,
        "architecture_classification_digest": "sha256:architecture-classification",
    }
    data.update(overrides)
    return data


def _closure(attestation=None, **overrides):
    return build_provider_invocation_denial_closure_manifest(
        _attestation() if attestation is None else attestation,
        closure_ref=overrides.pop("closure_ref", "phase100-denial-runway-closure"),
        accepted_evidence_codes=overrides.pop("accepted_evidence_codes", ("phase95", "phase96", "phase97", "phase98", "phase99")),
        approved_constraint_codes=overrides.pop("approved_constraint_codes", ("metadata_only", "provider_invocation_release_blocked")),
        guardrail_summary=overrides.pop("guardrail_summary", _guardrail()),
        **overrides,
    )


def _snapshot(closure=None, **overrides):
    manifest = _closure() if closure is None else closure
    return build_provider_invocation_denial_enforcement_snapshot(
        manifest,
        architecture_classification=overrides.pop("architecture_classification", _arch()),
        **overrides,
    )


def _codes(snapshot):
    return set(explain_provider_invocation_denial_enforcement_findings(snapshot))


def test_clean_phase100_closure_produces_clean_enforcement_snapshot_while_release_blocked():
    snapshot = _snapshot()
    assert snapshot.enforcement_status == ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_CLEAN
    assert provider_invocation_denial_enforcement_ready(snapshot)
    assert provider_invocation_denial_enforcement_blocks_release(snapshot)
    assert snapshot.blocker_posture.provider_invocation_blocked is True
    assert snapshot.blocker_posture.real_transport_registration_blocked is True
    assert snapshot.blocker_posture.credentials_blocked is True
    assert snapshot.blocker_posture.endpoints_blocked is True
    assert snapshot.blocker_posture.clients_blocked is True
    assert snapshot.blocker_posture.provider_sdks_blocked is True
    assert snapshot.blocker_posture.network_egress_blocked is True
    assert snapshot.blocker_posture.prompt_text_export_blocked is True
    assert snapshot.blocker_posture.runtime_authority_blocked is True
    assert snapshot.blocker_posture.prompt_assembler_modification_blocked is True
    assert snapshot.blocker_posture.export_io_blocked is True
    summary = summarize_provider_invocation_denial_enforcement_snapshot(snapshot)
    assert summary["release_blocked"] is True
    assert summary["metadata_only"] is True
    assert summary["no_provider"] is True
    assert summary["no_clearance"] is True
    assert not validate_provider_invocation_denial_enforcement_snapshot(snapshot)


def test_sealed_with_conditions_remains_blocked():
    conditioned = _closure(_attestation(decision=ProviderInvocationDenialAttestationDecision.ATTEST_WITH_CONDITIONS))
    snapshot = _snapshot(conditioned)
    assert snapshot.enforcement_status == ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_BLOCKED
    assert "phase100_sealed_with_conditions_blocked" in _codes(snapshot)
    assert provider_invocation_denial_enforcement_blocks_release(snapshot)


def test_missing_phase100_evidence_fails_closed():
    snapshot = build_provider_invocation_denial_enforcement_snapshot(None, architecture_classification=_arch())
    assert snapshot.enforcement_status == ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_INCOMPLETE
    assert "phase100_closure_manifest_missing" in _codes(snapshot)
    assert not provider_invocation_denial_enforcement_ready(snapshot)


def test_digest_mismatch_fails_closed():
    snapshot = _snapshot(expected_phase100_closure_digest="sha256:not-the-closure")
    assert snapshot.enforcement_status == ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_CONTRADICTED
    assert "expected_phase100_closure_digest_mismatch" in _codes(snapshot)


def test_contradictory_linked_metadata_fails_closed():
    snapshot = _snapshot(architecture_classification=_arch(contradictory=True, provider_invocation_allowed=True))
    assert snapshot.enforcement_status == ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_CONTRADICTED
    assert "architecture_classification_contradiction" in _codes(snapshot)


def test_unblock_approval_clearance_text_fails_closed():
    snapshot = _snapshot(rationale="clearance granted and release approved; unblock provider")
    assert snapshot.enforcement_status == ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_CONTRADICTED
    codes = _codes(snapshot)
    assert any(code.startswith("metadata_marker_detected:unblock") for code in codes)
    assert not provider_invocation_denial_enforcement_grants_no_clearance(snapshot)
    assert not provider_invocation_denial_enforcement_grants_no_unblock(snapshot)


def test_sensitive_material_markers_fail_closed():
    snapshot = _snapshot(rationale="api_key bearer token password private_key authorization")
    assert snapshot.enforcement_status == ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_CONTRADICTED
    assert any(code.startswith("metadata_marker_detected:sensitive") for code in _codes(snapshot))
    assert not provider_invocation_denial_enforcement_contains_no_secret(snapshot)


def test_provider_network_export_runtime_markers_fail_closed():
    flags = {
        "provider_invocation_performed": True,
        "network_egress_performed": True,
        "export_io_performed": True,
        "runtime_authority_granted": True,
        "prompt_assembler_modified": True,
    }
    for field, value in flags.items():
        snapshot = _snapshot(**{field: value})
        assert snapshot.enforcement_status == ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_CONTRADICTED
        assert f"authority_detected:{field}" in _codes(snapshot)


def test_predicate_helpers_stay_conservative():
    clean = _snapshot()
    assert provider_invocation_denial_enforcement_is_metadata_only(clean)
    assert provider_invocation_denial_enforcement_contains_no_provider(clean)
    assert provider_invocation_denial_enforcement_contains_no_network(clean)
    assert provider_invocation_denial_enforcement_contains_no_export(clean)
    assert provider_invocation_denial_enforcement_contains_no_prompt_text(clean)
    assert provider_invocation_denial_enforcement_contains_no_secret(clean)
    assert provider_invocation_denial_enforcement_contains_no_endpoint(clean)
    assert provider_invocation_denial_enforcement_contains_no_client(clean)
    assert provider_invocation_denial_enforcement_contains_no_runtime_authority(clean)
    assert provider_invocation_denial_enforcement_grants_no_clearance(clean)
    assert provider_invocation_denial_enforcement_grants_no_unblock(clean)
    assert not provider_invocation_denial_enforcement_is_metadata_only(_snapshot(provider_invocation_performed=True))
    assert not provider_invocation_denial_enforcement_contains_no_network(_snapshot(network_egress_performed=True))
    assert not provider_invocation_denial_enforcement_contains_no_export(_snapshot(export_io_performed=True))
    assert not provider_invocation_denial_enforcement_contains_no_runtime_authority(_snapshot(runtime_authority_granted=True))


def test_deterministic_digest_behavior():
    first = _snapshot()
    second = _snapshot()
    assert first.enforcement_digest == second.enforcement_digest
    assert first.enforcement_digest == compute_provider_invocation_denial_enforcement_digest(first)
    variant = _snapshot(_closure(closure_ref="phase100-other-denial-closure"))
    assert variant.enforcement_digest != first.enforcement_digest
    tampered = replace(first, enforcement_ref="phase101-other")
    assert any(finding.code == "enforcement_digest_mismatch" for finding in validate_provider_invocation_denial_enforcement_snapshot(tampered))


def test_no_prompt_assembler_modification_or_runtime_provider_network_export_authority():
    source = MODULE_PATH.read_text()
    assert "from prompt_assembler" not in source
    assert "import prompt_assembler" not in source
    snapshot = _snapshot()
    assert snapshot.prompt_assembler_modified is False
    assert snapshot.provider_invocation_performed is False
    assert snapshot.real_transport_registered is False
    assert snapshot.provider_sdks_imported is False
    assert snapshot.network_egress_performed is False
    assert snapshot.export_io_performed is False
    assert PROMPT_ASSEMBLER_PATH.exists()


def test_phase75_guardrail_scans_phase101_module_cleanly():
    report = scan_context_hygiene_prompt_boundaries(paths=[MODULE_PATH])
    assert report.ok, summarize_context_hygiene_prompt_boundary_scan(report)
    default_report = scan_context_hygiene_prompt_boundaries()
    assert default_report.ok, summarize_context_hygiene_prompt_boundary_scan(default_report)
