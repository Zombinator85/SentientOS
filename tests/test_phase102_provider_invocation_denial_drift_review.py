from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from scripts.verify_context_hygiene_prompt_boundaries import DEFAULT_SCAN_TARGETS
from sentientos.context_hygiene.prompt_provider_invocation_denial_attestation import ProviderInvocationDenialAttestationDecision
from sentientos.context_hygiene.prompt_provider_invocation_denial_closure import ProviderInvocationReleaseBlockerStatus
from sentientos.context_hygiene.prompt_provider_invocation_denial_drift_review import (
    ProviderInvocationDenialDriftDimensionStatus,
    ProviderInvocationDenialDriftReviewStatus,
    build_provider_invocation_denial_drift_review,
    compute_provider_invocation_denial_drift_review_digest,
    explain_provider_invocation_denial_drift_review_findings,
    provider_invocation_denial_drift_review_blocks_release,
    provider_invocation_denial_drift_review_clean_or_fail_closed,
    provider_invocation_denial_drift_review_contains_no_client,
    provider_invocation_denial_drift_review_contains_no_endpoint,
    provider_invocation_denial_drift_review_contains_no_export,
    provider_invocation_denial_drift_review_contains_no_network,
    provider_invocation_denial_drift_review_contains_no_prompt_text,
    provider_invocation_denial_drift_review_contains_no_provider,
    provider_invocation_denial_drift_review_contains_no_runtime_authority,
    provider_invocation_denial_drift_review_contains_no_secret,
    provider_invocation_denial_drift_review_grants_no_clearance,
    provider_invocation_denial_drift_review_grants_no_unblock,
    provider_invocation_denial_drift_review_is_metadata_only,
    provider_invocation_denial_drift_review_ready,
    summarize_provider_invocation_denial_drift_review,
    validate_provider_invocation_denial_drift_review,
)
from sentientos.context_hygiene.prompt_provider_invocation_denial_enforcement import ProviderInvocationDenialEnforcementStatus
from tests.test_phase101_provider_invocation_denial_enforcement import _arch, _closure, _snapshot
from tests.test_phase99_provider_invocation_denial_attestation import _attestation

MODULE_PATH = Path("sentientos/context_hygiene/prompt_provider_invocation_denial_drift_review.py")
PROMPT_ASSEMBLER_PATH = Path("prompt_assembler.py")


def _prompt_scan(**overrides):
    data = {
        "status": "boundary_clean",
        "scanned_paths": tuple(DEFAULT_SCAN_TARGETS) + ("sentientos/context_hygiene/prompt_provider_invocation_denial_drift_review.py",),
        "finding_count": 0,
        "findings": (),
        "allowlist_labels": ("metadata_only", "id", "digest", "status", "count", "boolean", "guardrail", "classification", "coverage", "negative_capability", "release_blocked"),
        "allowlist_metadata_only": True,
    }
    data.update(overrides)
    return data


def _review(closure=None, snapshot=None, **overrides):
    manifest = _closure() if closure is None else closure
    enforcement = _snapshot(manifest) if snapshot is None else snapshot
    return build_provider_invocation_denial_drift_review(
        manifest,
        enforcement,
        architecture_classification=overrides.pop("architecture_classification", _arch()),
        prompt_boundary_scan=overrides.pop("prompt_boundary_scan", _prompt_scan()),
        **overrides,
    )


def _codes(review):
    return set(explain_provider_invocation_denial_drift_review_findings(review))


def test_clean_phase100_and_phase101_and_architecture_metadata_produce_clean_release_blocked_review():
    review = _review()
    assert review.drift_status == ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CLEAN
    assert provider_invocation_denial_drift_review_ready(review)
    assert provider_invocation_denial_drift_review_blocks_release(review)
    assert provider_invocation_denial_drift_review_is_metadata_only(review)
    assert provider_invocation_denial_drift_review_clean_or_fail_closed(review)
    assert provider_invocation_denial_drift_review_contains_no_provider(review)
    assert provider_invocation_denial_drift_review_contains_no_network(review)
    assert provider_invocation_denial_drift_review_contains_no_export(review)
    assert provider_invocation_denial_drift_review_contains_no_prompt_text(review)
    assert provider_invocation_denial_drift_review_contains_no_secret(review)
    assert provider_invocation_denial_drift_review_contains_no_endpoint(review)
    assert provider_invocation_denial_drift_review_contains_no_client(review)
    assert provider_invocation_denial_drift_review_contains_no_runtime_authority(review)
    assert provider_invocation_denial_drift_review_grants_no_clearance(review)
    assert provider_invocation_denial_drift_review_grants_no_unblock(review)
    assert review.dimensions.closure_enforcement_status_consistency == ProviderInvocationDenialDriftDimensionStatus.CONSISTENT
    assert review.dimensions.release_blocker_consistency == ProviderInvocationDenialDriftDimensionStatus.CONSISTENT
    assert review.dimensions.architecture_classification_consistency == ProviderInvocationDenialDriftDimensionStatus.CONSISTENT
    assert review.dimensions.prompt_boundary_scan_coverage_consistency == ProviderInvocationDenialDriftDimensionStatus.CONSISTENT
    summary = summarize_provider_invocation_denial_drift_review(review)
    assert summary["release_blocked"] is True
    assert summary["metadata_only"] is True
    assert not validate_provider_invocation_denial_drift_review(review)


def test_sealed_with_conditions_remains_blocked():
    conditioned = _closure(_attestation(decision=ProviderInvocationDenialAttestationDecision.ATTEST_WITH_CONDITIONS))
    review = _review(conditioned)
    assert review.drift_status == ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_BLOCKED
    assert "closure_enforcement_conditioned_blocked" in _codes(review)
    assert provider_invocation_denial_drift_review_blocks_release(review)


def test_missing_phase100_metadata_fails_closed():
    review = build_provider_invocation_denial_drift_review(None, _snapshot(), architecture_classification=_arch(), prompt_boundary_scan=_prompt_scan())
    assert review.drift_status == ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_INCOMPLETE
    assert "phase100_closure_metadata_missing" in _codes(review)
    assert provider_invocation_denial_drift_review_blocks_release(review)


def test_missing_phase101_metadata_fails_closed():
    review = build_provider_invocation_denial_drift_review(_closure(), None, architecture_classification=_arch(), prompt_boundary_scan=_prompt_scan())
    assert review.drift_status == ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_INCOMPLETE
    assert "phase101_enforcement_metadata_missing" in _codes(review)


def test_phase100_phase101_digest_mismatch_fails_closed():
    manifest = _closure()
    snapshot = replace(_snapshot(manifest), evidence=replace(_snapshot(manifest).evidence, expected_phase100_closure_digest="sha256:other"))
    review = _review(manifest, snapshot)
    assert review.drift_status == ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CONTRADICTED
    assert "phase100_phase101_digest_mismatch" in _codes(review)


def test_closure_enforcement_status_contradiction_fails_closed():
    manifest = _closure()
    snapshot = replace(_snapshot(manifest), enforcement_status=ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_BLOCKED)
    review = _review(manifest, snapshot)
    assert review.drift_status == ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CONTRADICTED
    assert "closure_enforcement_status_contradiction" in _codes(review)


def test_release_blocker_contradiction_fails_closed():
    manifest = _closure(release_blocker_status=ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_UNBLOCKED_FORBIDDEN)
    review = _review(manifest, _snapshot(manifest))
    assert review.drift_status == ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CONTRADICTED
    assert "release_blocker_contradiction" in _codes(review)


def test_architecture_classification_contradiction_fails_closed():
    review = _review(architecture_classification=_arch(provider_invocation_allowed=True))
    assert review.drift_status == ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CONTRADICTED
    assert "architecture_classification_contradiction" in _codes(review)


def test_prompt_boundary_coverage_gap_fails_closed():
    targets = tuple(path for path in DEFAULT_SCAN_TARGETS if not path.endswith("prompt_provider_invocation_denial_enforcement.py"))
    review = _review(prompt_boundary_scan=_prompt_scan(scanned_paths=targets))
    assert review.drift_status == ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_INCOMPLETE
    assert "prompt_boundary_scan_coverage_gap" in _codes(review)


def test_allowlist_broadening_marker_fails_closed():
    review = _review(prompt_boundary_scan=_prompt_scan(allowlist_labels=("metadata_only", "provider_client_runtime")))
    assert review.drift_status == ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CONTRADICTED
    assert "allowlist_broadening_detected" in _codes(review)


def test_unblock_approval_clearance_text_fails_closed():
    review = _review(prompt_boundary_scan=_prompt_scan(notes="release approved and unblock provider with clearance granted"))
    assert review.drift_status == ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CONTRADICTED
    assert any(code.startswith("metadata_marker_detected:unblock") for code in _codes(review))


def test_sensitive_material_markers_fail_closed():
    review = _review(prompt_boundary_scan=_prompt_scan(notes="api_key bearer token password private_key authorization"))
    assert review.drift_status == ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CONTRADICTED
    assert any(code.startswith("metadata_marker_detected:sensitive") for code in _codes(review))
    assert not provider_invocation_denial_drift_review_contains_no_secret(review)


def test_provider_network_export_runtime_markers_fail_closed():
    markers = "invoke send_to_provider chat.completions upload email webhook runtime handle action execution"
    review = _review(prompt_boundary_scan=_prompt_scan(notes=markers))
    assert review.drift_status == ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CONTRADICTED
    assert any(code.startswith("metadata_marker_detected:provider_invocation") for code in _codes(review))
    assert any(code.startswith("metadata_marker_detected:export_destination") for code in _codes(review))
    assert any(code.startswith("metadata_marker_detected:runtime") for code in _codes(review))


def test_deterministic_digest_behavior():
    first = _review()
    second = _review()
    assert first.drift_digest == compute_provider_invocation_denial_drift_review_digest(first)
    assert second.drift_digest == first.drift_digest
    assert _review(prompt_boundary_scan=_prompt_scan(allowlist_labels=("metadata_only",))).drift_digest != first.drift_digest


def test_no_prompt_assembler_modification_and_no_runtime_provider_network_export_authority():
    before = PROMPT_ASSEMBLER_PATH.read_bytes()
    review = _review()
    after = PROMPT_ASSEMBLER_PATH.read_bytes()
    assert before == after
    assert review.prompt_assembler_modified is False
    assert review.provider_invocation_performed is False
    assert review.network_egress_performed is False
    assert review.export_io_performed is False
    assert review.artifact_bodies_read is False
    assert MODULE_PATH.read_text(encoding="utf-8")
