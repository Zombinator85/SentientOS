from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from scripts.verify_context_hygiene_prompt_boundaries import DEFAULT_SCAN_TARGETS
from sentientos.context_hygiene.prompt_provider_invocation_denial_custody_checkpoint import (
    ProviderInvocationDenialCustodyCheckpointStatus,
    ProviderInvocationDenialCustodyDimensionStatus,
    build_provider_invocation_denial_custody_checkpoint,
    compute_provider_invocation_denial_custody_checkpoint_digest,
    explain_provider_invocation_denial_custody_checkpoint_findings,
    provider_invocation_denial_custody_checkpoint_audit_verified,
    provider_invocation_denial_custody_checkpoint_blocks_release,
    provider_invocation_denial_custody_checkpoint_clean_or_fail_closed,
    provider_invocation_denial_custody_checkpoint_contains_no_client,
    provider_invocation_denial_custody_checkpoint_contains_no_endpoint,
    provider_invocation_denial_custody_checkpoint_contains_no_export,
    provider_invocation_denial_custody_checkpoint_contains_no_network,
    provider_invocation_denial_custody_checkpoint_contains_no_prompt_text,
    provider_invocation_denial_custody_checkpoint_contains_no_provider,
    provider_invocation_denial_custody_checkpoint_contains_no_runtime_authority,
    provider_invocation_denial_custody_checkpoint_contains_no_secret,
    provider_invocation_denial_custody_checkpoint_grants_no_clearance,
    provider_invocation_denial_custody_checkpoint_grants_no_unblock,
    provider_invocation_denial_custody_checkpoint_immutable_verified,
    provider_invocation_denial_custody_checkpoint_is_metadata_only,
    provider_invocation_denial_custody_checkpoint_ready,
    summarize_provider_invocation_denial_custody_checkpoint,
    validate_provider_invocation_denial_custody_checkpoint,
)
from sentientos.context_hygiene.prompt_provider_invocation_denial_closure import ProviderInvocationDenialClosureStatus
from sentientos.context_hygiene.prompt_provider_invocation_denial_enforcement import ProviderInvocationDenialEnforcementStatus
from tests.test_phase101_provider_invocation_denial_enforcement import _arch, _closure, _snapshot
from tests.test_phase102_provider_invocation_denial_drift_review import _prompt_scan as _phase102_prompt_scan, _review

MODULE_PATH = Path("sentientos/context_hygiene/prompt_provider_invocation_denial_custody_checkpoint.py")
PROMPT_ASSEMBLER_PATH = Path("prompt_assembler.py")


def _strict_audit(**overrides):
    data = {"status": "passed", "command_result": "passed", "verified": True, "strict": True}
    data.update(overrides)
    return data


def _immutable(**overrides):
    data = {"status": "verified", "command_result": "passed", "verified": True}
    data.update(overrides)
    return data


def _prompt_scan(**overrides):
    data = _phase102_prompt_scan(
        scanned_paths=tuple(DEFAULT_SCAN_TARGETS)
        + (
            "sentientos/context_hygiene/prompt_provider_invocation_denial_drift_review.py",
            "sentientos/context_hygiene/prompt_provider_invocation_denial_custody_checkpoint.py",
        ),
        allowlist_labels=(
            "metadata_only",
            "id",
            "digest",
            "status",
            "count",
            "boolean",
            "guardrail",
            "classification",
            "coverage",
            "negative_capability",
            "release_blocked",
            "command_result_label",
            "audit_verified",
            "immutable_verified",
        ),
    )
    data.update(overrides)
    return data


def _checkpoint(closure=None, snapshot=None, review=None, **overrides):
    phase100 = _closure() if closure is None else closure
    phase101 = _snapshot(phase100) if snapshot is None else snapshot
    phase102 = _review(phase100, phase101) if review is None else review
    return build_provider_invocation_denial_custody_checkpoint(
        phase100,
        phase101,
        phase102,
        strict_audit_verification=overrides.pop("strict_audit_verification", _strict_audit()),
        immutable_manifest_verification=overrides.pop("immutable_manifest_verification", _immutable()),
        architecture_classification=overrides.pop("architecture_classification", _arch()),
        prompt_boundary_scan=overrides.pop("prompt_boundary_scan", _prompt_scan()),
        **overrides,
    )


def _codes(checkpoint):
    return set(explain_provider_invocation_denial_custody_checkpoint_findings(checkpoint))


def test_clean_phase100_phase101_phase102_and_verifications_produce_clean_release_blocked_checkpoint():
    checkpoint = _checkpoint()
    assert checkpoint.checkpoint_status == ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CLEAN
    assert provider_invocation_denial_custody_checkpoint_ready(checkpoint)
    assert provider_invocation_denial_custody_checkpoint_blocks_release(checkpoint)
    assert provider_invocation_denial_custody_checkpoint_is_metadata_only(checkpoint)
    assert provider_invocation_denial_custody_checkpoint_clean_or_fail_closed(checkpoint)
    assert provider_invocation_denial_custody_checkpoint_audit_verified(checkpoint)
    assert provider_invocation_denial_custody_checkpoint_immutable_verified(checkpoint)
    assert provider_invocation_denial_custody_checkpoint_contains_no_provider(checkpoint)
    assert provider_invocation_denial_custody_checkpoint_contains_no_network(checkpoint)
    assert provider_invocation_denial_custody_checkpoint_contains_no_export(checkpoint)
    assert provider_invocation_denial_custody_checkpoint_contains_no_prompt_text(checkpoint)
    assert provider_invocation_denial_custody_checkpoint_contains_no_secret(checkpoint)
    assert provider_invocation_denial_custody_checkpoint_contains_no_endpoint(checkpoint)
    assert provider_invocation_denial_custody_checkpoint_contains_no_client(checkpoint)
    assert provider_invocation_denial_custody_checkpoint_contains_no_runtime_authority(checkpoint)
    assert provider_invocation_denial_custody_checkpoint_grants_no_clearance(checkpoint)
    assert provider_invocation_denial_custody_checkpoint_grants_no_unblock(checkpoint)
    assert checkpoint.dimensions.phase100_closure_custody == ProviderInvocationDenialCustodyDimensionStatus.CONSISTENT
    assert checkpoint.dimensions.phase101_enforcement_custody == ProviderInvocationDenialCustodyDimensionStatus.CONSISTENT
    assert checkpoint.dimensions.phase102_drift_review_custody == ProviderInvocationDenialCustodyDimensionStatus.CONSISTENT
    assert checkpoint.dimensions.strict_audit_verification_custody == ProviderInvocationDenialCustodyDimensionStatus.CONSISTENT
    assert checkpoint.dimensions.immutable_manifest_verification_custody == ProviderInvocationDenialCustodyDimensionStatus.CONSISTENT
    summary = summarize_provider_invocation_denial_custody_checkpoint(checkpoint)
    assert summary["release_blocked"] is True
    assert summary["metadata_only"] is True
    assert summary["audit_verified"] is True
    assert summary["immutable_verified"] is True
    assert not validate_provider_invocation_denial_custody_checkpoint(checkpoint)


def test_missing_phase100_metadata_fails_closed():
    checkpoint = build_provider_invocation_denial_custody_checkpoint(
        None,
        _snapshot(),
        _review(),
        strict_audit_verification=_strict_audit(),
        immutable_manifest_verification=_immutable(),
        architecture_classification=_arch(),
        prompt_boundary_scan=_prompt_scan(),
    )
    assert checkpoint.checkpoint_status == ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_INCOMPLETE
    assert "phase100_closure_metadata_missing" in _codes(checkpoint)
    assert not provider_invocation_denial_custody_checkpoint_ready(checkpoint)


def test_missing_phase101_metadata_fails_closed():
    checkpoint = build_provider_invocation_denial_custody_checkpoint(
        _closure(),
        None,
        _review(),
        strict_audit_verification=_strict_audit(),
        immutable_manifest_verification=_immutable(),
        architecture_classification=_arch(),
        prompt_boundary_scan=_prompt_scan(),
    )
    assert checkpoint.checkpoint_status == ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_INCOMPLETE
    assert "phase101_enforcement_metadata_missing" in _codes(checkpoint)


def test_missing_phase102_metadata_fails_closed():
    checkpoint = build_provider_invocation_denial_custody_checkpoint(
        _closure(),
        _snapshot(),
        None,
        strict_audit_verification=_strict_audit(),
        immutable_manifest_verification=_immutable(),
        architecture_classification=_arch(),
        prompt_boundary_scan=_prompt_scan(),
    )
    assert checkpoint.checkpoint_status == ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_INCOMPLETE
    assert "phase102_drift_review_metadata_missing" in _codes(checkpoint)


def test_phase_digest_mismatch_fails_closed():
    checkpoint = _checkpoint(review=replace(_review(), evidence_summary=replace(_review().evidence_summary, phase100_closure_digest="sha256:not-phase100")))
    assert checkpoint.checkpoint_status == ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CONTRADICTED
    codes = _codes(checkpoint)
    assert "phase100_phase102_digest_mismatch" in codes or "phase102_drift_digest_mismatch" in codes


def test_phase_status_contradiction_fails_closed():
    closure = replace(_closure(), closure_status=ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_BLOCKED)
    checkpoint = _checkpoint(closure=closure, snapshot=_snapshot(_closure()), review=_review())
    assert checkpoint.checkpoint_status == ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CONTRADICTED
    assert any("status_contradiction" in code for code in _codes(checkpoint))


def test_failed_strict_audit_verification_fails_closed():
    checkpoint = _checkpoint(strict_audit_verification=_strict_audit(status="failed", command_result="failed", verified=False))
    assert checkpoint.checkpoint_status == ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CONTRADICTED
    assert "strict_audit_verification_failed" in _codes(checkpoint)
    assert not provider_invocation_denial_custody_checkpoint_audit_verified(checkpoint)


def test_failed_immutable_verification_fails_closed():
    checkpoint = _checkpoint(immutable_manifest_verification=_immutable(status="failed", command_result="failed", verified=False))
    assert checkpoint.checkpoint_status == ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CONTRADICTED
    assert "immutable_manifest_verification_failed" in _codes(checkpoint)
    assert not provider_invocation_denial_custody_checkpoint_immutable_verified(checkpoint)


def test_architecture_classification_contradiction_fails_closed():
    checkpoint = _checkpoint(architecture_classification=_arch(contradictory=True, provider_invocation_allowed=True))
    assert checkpoint.checkpoint_status == ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CONTRADICTED
    assert "architecture_classification_contradiction" in _codes(checkpoint)


def test_prompt_boundary_coverage_gap_fails_closed():
    checkpoint = _checkpoint(prompt_boundary_scan=_prompt_scan(scanned_paths=("sentientos/context_hygiene/prompt_provider_invocation_denial_closure.py",)))
    assert checkpoint.checkpoint_status == ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_INCOMPLETE
    assert "prompt_boundary_scan_coverage_gap" in _codes(checkpoint)


def test_allowlist_broadening_marker_fails_closed():
    checkpoint = _checkpoint(allowlist_labels=("metadata_only", "provider_runtime_authority"))
    assert checkpoint.checkpoint_status == ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CONTRADICTED
    assert "allowlist_broadening_detected" in _codes(checkpoint)


def test_unblock_approval_clearance_text_fails_closed():
    checkpoint = _checkpoint(checkpoint_label="clearance granted and release approved; unblock provider")
    assert checkpoint.checkpoint_status == ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CONTRADICTED
    codes = _codes(checkpoint)
    assert any(code.startswith("metadata_marker_detected:unblock") for code in codes)
    assert not provider_invocation_denial_custody_checkpoint_grants_no_clearance(checkpoint)
    assert not provider_invocation_denial_custody_checkpoint_grants_no_unblock(checkpoint)


def test_sensitive_material_markers_fail_closed():
    checkpoint = _checkpoint(checkpoint_label="api_key bearer token password private_key authorization")
    assert checkpoint.checkpoint_status == ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CONTRADICTED
    assert any(code.startswith("metadata_marker_detected:sensitive") for code in _codes(checkpoint))
    assert not provider_invocation_denial_custody_checkpoint_contains_no_secret(checkpoint)


def test_provider_network_export_runtime_prompt_text_markers_fail_closed():
    labels = {
        "provider_invocation_performed": "provider invocation",
        "network_egress_performed": "network authority",
        "export_io_performed": "export authority",
        "runtime_authority_detected": "runtime handle",
        "prompt_text_included": "prompt_text",
    }
    for field in labels:
        checkpoint = _checkpoint(**{field: True})
        assert checkpoint.checkpoint_status == ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CONTRADICTED
        assert f"authority_detected:{field}" in _codes(checkpoint)


def test_prompt_assembler_modification_marker_fails_closed():
    checkpoint = _checkpoint(prompt_assembler_modified=True)
    assert checkpoint.checkpoint_status == ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CONTRADICTED
    assert "authority_detected:prompt_assembler_modified" in _codes(checkpoint)


def test_deterministic_digest_behavior():
    first = _checkpoint()
    second = _checkpoint()
    assert first.custody_digest == second.custody_digest
    assert first.custody_digest == compute_provider_invocation_denial_custody_checkpoint_digest(first)
    variant = _checkpoint(checkpoint_ref="phase103-other-custody-checkpoint")
    assert variant.custody_digest != first.custody_digest
    tampered = replace(first, checkpoint_ref="phase103-tampered")
    assert any(finding.code == "custody_digest_mismatch" for finding in validate_provider_invocation_denial_custody_checkpoint(tampered))


def test_no_prompt_assembler_modification_or_runtime_provider_network_export_authority():
    source = MODULE_PATH.read_text()
    assert "from prompt_assembler" not in source
    assert "import prompt_assembler" not in source
    checkpoint = _checkpoint()
    assert checkpoint.prompt_assembler_modified is False
    assert checkpoint.provider_invocation_performed is False
    assert checkpoint.network_egress_performed is False
    assert checkpoint.export_io_performed is False
    assert checkpoint.runtime_authority_detected is False
    assert PROMPT_ASSEMBLER_PATH.exists()
    assert _snapshot().enforcement_status == ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_CLEAN
