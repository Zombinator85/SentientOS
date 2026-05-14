from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.reviewer_proof_bundle import (
    DEFERRED_ACTION_LABELS,
    ReviewerProofBundleArtifact,
    build_default_reviewer_proof_commands,
    build_reviewer_proof_bundle_payload,
    reviewer_proof_artifact_digest,
    reviewer_proof_bundle_manifest_digest,
    summarize_reviewer_proof_bundle_manifest,
    validate_reviewer_proof_bundle_manifest,
)

pytestmark = pytest.mark.no_legacy_skip

FIXED_CREATED_AT = "2025-07-30T00:00:00+00:00"


def test_default_bundle_payload_is_deterministic_with_fixed_created_at() -> None:
    first = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    second = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    assert first["manifest"].to_dict() == second["manifest"].to_dict()
    assert first["artifacts"] == second["artifacts"]
    assert first["manifest"].created_at == FIXED_CREATED_AT
    assert first["manifest"].bundle_status == "reviewer_proof_bundle_ready"


def test_manifest_validates_and_digests_are_deterministic() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    manifest = payload["manifest"]
    validation = validate_reviewer_proof_bundle_manifest(manifest)
    assert validation.ok, validation.findings
    assert reviewer_proof_bundle_manifest_digest(manifest) == manifest.digest
    assert reviewer_proof_artifact_digest(payload["artifacts"]["trace_json"]) == next(
        artifact.digest for artifact in manifest.artifact_records if artifact.artifact_kind == "trace_json"
    )


def test_manifest_summary_is_metadata_only_and_reviewer_proof_only() -> None:
    manifest = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)["manifest"]
    summary = summarize_reviewer_proof_bundle_manifest(manifest)
    assert summary["metadata_only"] is True
    assert summary["reviewer_proof_only"] is True
    assert summary["live_host_collection_performed"] is False
    assert summary["live_authorization_granted"] is False
    assert summary["effect_performed"] is False
    assert summary["host_mutation_performed"] is False
    assert summary["network_performed"] is False
    assert summary["provider_invocation_performed"] is False
    assert summary["prompt_assembly_performed"] is False


def test_default_proof_commands_are_listed_and_not_run() -> None:
    commands = build_default_reviewer_proof_commands()
    assert commands
    assert all(command.status == "proof_command_not_run" for command in commands)
    assert all(command.executed is False for command in commands)
    rendered = [" ".join(command.command) for command in commands]
    assert "python scripts/build_host_embodiment_trace.py --validate-only" in rendered
    assert "python scripts/verify_context_hygiene_prompt_boundaries.py" in rendered


def test_bundle_includes_expected_artifacts_and_content() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    artifacts = payload["artifacts"]
    for key in [
        "trace_json",
        "trace_markdown",
        "trace_summary",
        "capability_registry_summary",
        "deferred_action_inventory",
        "proof_command_manifest",
        "reviewer_readme",
        "bundle_manifest",
    ]:
        assert key in artifacts
    assert "fake/sample" in artifacts["trace_summary"]
    assert "PWM presence is not control authority" in artifacts["trace_markdown"]
    assert "reviewer_proof_bundle" in artifacts["capability_registry_summary"]
    assert "real_fan_pwm_control" in artifacts["deferred_action_inventory"]
    assert "proof_command_not_run" in artifacts["proof_command_manifest"]


def test_deferred_actions_cover_non_mutating_boundary() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    manifest = payload["manifest"]
    for label in [
        "real_fan_pwm_control",
        "real_thermal_actuation",
        "real_power_profile_mutation",
        "real_service_restart",
        "real_file_cleanup",
        "provider_invocation",
        "network_egress",
        "prompt_assembly_export",
        "federation_transport_sync_adoption",
        "remote_execution",
    ]:
        assert label in manifest.deferred_capability_labels
        assert label in DEFERRED_ACTION_LABELS


@pytest.mark.parametrize(
    "flag",
    [
        "live_host_collection_performed",
        "live_authorization_granted",
        "effect_performed",
        "host_mutation_performed",
        "network_performed",
        "provider_invocation_performed",
        "prompt_assembly_performed",
    ],
)
def test_validation_rejects_forbidden_manifest_flags(flag: str) -> None:
    manifest = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)["manifest"]
    bad = replace(manifest, **{flag: True})
    result = validate_reviewer_proof_bundle_manifest(bad)
    assert not result.ok
    assert f"manifest_forbidden_flag:{flag}" in result.findings


@pytest.mark.parametrize(
    "flag",
    ["contains_live_host_data", "contains_prompt_text", "contains_secret_material", "contains_provider_material"],
)
def test_artifact_validation_rejects_forbidden_material_flags(flag: str) -> None:
    manifest = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)["manifest"]
    artifacts = list(manifest.artifact_records)
    artifacts[0] = replace(artifacts[0], **{flag: True})
    bad = replace(manifest, artifact_records=tuple(artifacts))
    result = validate_reviewer_proof_bundle_manifest(bad)
    assert not result.ok
    assert any(f"artifact_forbidden_flag:{artifacts[0].artifact_kind}:{flag}" == finding for finding in result.findings)


def test_validation_rejects_unknown_artifact_kind() -> None:
    manifest = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)["manifest"]
    artifacts = list(manifest.artifact_records)
    artifacts.append(
        ReviewerProofBundleArtifact(
            artifact_id="bad",
            artifact_kind="unknown",
            relative_path="bad.txt",
            media_type="text/plain",
            digest="sha256:bad",
            byte_count=3,
        )
    )
    result = validate_reviewer_proof_bundle_manifest(replace(manifest, artifact_records=tuple(artifacts)))
    assert not result.ok
    assert "unknown_artifact_kind:unknown" in result.findings


def test_bundle_includes_host_actuation_safety_gate_posture() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    assert "safety_gate_posture" in payload["artifacts"]
    assert "safety_gates.json" in payload["artifacts"]["bundle_manifest"]
    assert "Safety gates declare prerequisites only" in payload["artifacts"]["safety_gate_posture"]
    assert "safety_gates" in payload
    validation = validate_reviewer_proof_bundle_manifest(payload["manifest"])
    assert validation.ok, validation.findings
