from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.host_steward_boundary import (
    build_backend_adapter_authority_declaration,
    build_delegated_runner_boundary_profile,
    build_execution_containment_profile,
    build_host_steward_authority_profile,
    build_host_steward_boundary_wing,
    build_runner_boundary_violation_receipt,
    build_runner_capability_grant_scaffold,
    host_steward_boundary_digest,
    summarize_backend_adapter_authority_declaration,
    summarize_delegated_runner_boundary_profile,
    summarize_execution_containment_profile,
    summarize_host_steward_authority_profile,
    summarize_host_steward_boundary_wing,
    summarize_runner_boundary_assessment,
    summarize_runner_boundary_violation_receipt,
    summarize_runner_capability_grant_scaffold,
    assess_runner_boundary,
    validate_backend_adapter_authority_declaration,
    validate_delegated_runner_boundary_profile,
    validate_execution_containment_profile,
    validate_host_steward_authority_profile,
    validate_runner_boundary_assessment,
    validate_runner_boundary_violation_receipt,
    validate_runner_capability_grant_scaffold,
)

pytestmark = pytest.mark.no_legacy_skip

FIXED_CREATED_AT = "2025-07-30T00:00:00+00:00"


def test_default_host_steward_profile_models_broad_authority_without_runner_grant() -> None:
    profile = build_host_steward_authority_profile(created_at=FIXED_CREATED_AT)
    assert profile.authority_mode == "full_local_host_steward_mode"
    assert "host_steward_may_hold_broad_local_authority" in profile.allowed_top_level_authority_labels
    assert "delegated_runners_do_not_inherit_ambient_authority" in profile.prohibited_delegation_labels
    assert profile.grants_live_runner_authority is False
    assert profile.executes_runner is False
    assert profile.host_mutation_performed is False
    assert validate_host_steward_authority_profile(profile).ok
    assert summarize_host_steward_authority_profile(profile)["metadata_only"] is True


@pytest.mark.parametrize("runner", ["generated_code_runner", "plugin_runner", "federation_import_runner", "external_tool_runner", "unknown_runner"])
def test_untrusted_runner_defaults_no_network_no_host_mutation_metadata_or_dry_run(runner: str) -> None:
    boundary = build_delegated_runner_boundary_profile(boundary_id=f"{runner}-boundary", runner_trust_class=runner, created_at=FIXED_CREATED_AT)
    assert boundary.containment_class in {"metadata_only_containment", "dry_run_simulation_containment", "offline_no_network_containment"}
    assert "ambient_authority_inheritance" in boundary.blocked_actions
    assert "delegated_runners_do_not_inherit_ambient_authority" in boundary.denied_authority_labels
    assert "runner_must_not_use_network_by_default" in boundary.denied_authority_labels
    assert boundary.runner_executed is False
    assert boundary.host_mutation_performed is False
    assert validate_delegated_runner_boundary_profile(boundary).ok


def test_local_diagnostic_runner_boundary_can_reference_file_effect_without_broadening() -> None:
    boundary = build_delegated_runner_boundary_profile(
        boundary_id="local-diagnostic",
        runner_trust_class="bounded_builtin_runner",
        containment_class="local_file_effect_containment",
        allowed_authority_labels=("diagnostic_file_effect_mode",),
        created_at=FIXED_CREATED_AT,
    )
    assert boundary.boundary_status == "delegated_runner_boundary_ready"
    assert boundary.allowed_authority_labels == ("diagnostic_file_effect_mode",)
    assert "runner_network_egress" in boundary.blocked_actions
    assert "runner_shell_execution" in boundary.blocked_actions
    assert validate_delegated_runner_boundary_profile(boundary).ok


def test_containment_backend_grant_assessment_and_violation_are_metadata_only() -> None:
    profile = build_host_steward_authority_profile(created_at=FIXED_CREATED_AT)
    boundary = build_delegated_runner_boundary_profile(boundary_id="generated", runner_trust_class="generated_code_runner", created_at=FIXED_CREATED_AT)
    containment = build_execution_containment_profile(containment_id="containment", created_at=FIXED_CREATED_AT)
    backend = build_backend_adapter_authority_declaration(declaration_id="backend", adapter_label="future", created_at=FIXED_CREATED_AT)
    scaffold = build_runner_capability_grant_scaffold(scaffold_id="scaffold", boundary_id=boundary.boundary_id, containment_id=containment.containment_id, backend_authority_declaration_id=backend.declaration_id, created_at=FIXED_CREATED_AT)
    assessment = assess_runner_boundary(profile, boundary, containment, scaffold, created_at=FIXED_CREATED_AT)
    violation = build_runner_boundary_violation_receipt(receipt_id="violation", assessment_id=assessment.assessment_id, created_at=FIXED_CREATED_AT)

    assert containment.containment_enforced_live is False
    assert backend.backend_loaded is False and backend.backend_invoked is False
    assert scaffold.live_runner_grant_issued is False
    assert assessment.authorizes_runner_execution is False
    assert violation.authorizes_runner_execution is False
    assert all(item.host_mutation_performed is False for item in (containment, backend, scaffold, assessment, violation))
    assert validate_execution_containment_profile(containment).ok
    assert validate_backend_adapter_authority_declaration(backend).ok
    assert validate_runner_capability_grant_scaffold(scaffold).ok
    assert validate_runner_boundary_assessment(assessment).ok
    assert validate_runner_boundary_violation_receipt(violation).ok
    assert summarize_execution_containment_profile(containment)["containment_enforced_live"] is False
    assert summarize_backend_adapter_authority_declaration(backend)["backend_invoked"] is False
    assert summarize_runner_capability_grant_scaffold(scaffold)["live_runner_grant_issued"] is False
    assert summarize_runner_boundary_assessment(assessment)["authorizes_runner_execution"] is False
    assert summarize_runner_boundary_violation_receipt(violation)["runner_executed"] is False


@pytest.mark.parametrize(
    "builder,validator,field",
    [
        (lambda: build_host_steward_authority_profile(), validate_host_steward_authority_profile, "executes_runner"),
        (lambda: build_delegated_runner_boundary_profile(boundary_id="b"), validate_delegated_runner_boundary_profile, "runner_executed"),
        (lambda: build_execution_containment_profile(containment_id="c"), validate_execution_containment_profile, "containment_enforced_live"),
        (lambda: build_backend_adapter_authority_declaration(declaration_id="d", adapter_label="a"), validate_backend_adapter_authority_declaration, "backend_loaded"),
        (lambda: build_backend_adapter_authority_declaration(declaration_id="d", adapter_label="a"), validate_backend_adapter_authority_declaration, "backend_invoked"),
        (lambda: build_runner_capability_grant_scaffold(scaffold_id="s", boundary_id="b", containment_id="c"), validate_runner_capability_grant_scaffold, "live_runner_grant_issued"),
    ],
)
def test_validation_rejects_forbidden_true_flags(builder, validator, field: str) -> None:
    bad = replace(builder(), **{field: True})
    result = validator(bad)
    assert not result.ok
    assert f"forbidden_flag:{field}" in result.findings


def test_validation_rejects_host_mutation_and_missing_ambient_block() -> None:
    boundary = build_delegated_runner_boundary_profile(boundary_id="b")
    bad_mutation = replace(boundary, host_mutation_performed=True)
    assert "forbidden_flag:host_mutation_performed" in validate_delegated_runner_boundary_profile(bad_mutation).findings
    bad_block = replace(boundary, blocked_actions=tuple(action for action in boundary.blocked_actions if action != "ambient_authority_inheritance"))
    assert "missing_blocked_action:ambient_authority_inheritance" in validate_delegated_runner_boundary_profile(bad_block).findings


def test_digests_are_deterministic_and_change_on_meaningful_metadata() -> None:
    first = build_delegated_runner_boundary_profile(boundary_id="b", runner_trust_class="plugin_runner", created_at=FIXED_CREATED_AT)
    second = build_delegated_runner_boundary_profile(boundary_id="b", runner_trust_class="plugin_runner", created_at=FIXED_CREATED_AT)
    changed = build_delegated_runner_boundary_profile(boundary_id="b2", runner_trust_class="plugin_runner", created_at=FIXED_CREATED_AT)
    assert first.digest == second.digest == host_steward_boundary_digest(first)
    assert first.digest != changed.digest
    assert summarize_delegated_runner_boundary_profile(first)["metadata_only"] is True


def test_host_steward_boundary_wing_proves_no_ambient_inheritance_or_execution() -> None:
    wing = build_host_steward_boundary_wing(created_at=FIXED_CREATED_AT)
    summary = summarize_host_steward_boundary_wing(wing)
    assert summary["proof_delegated_runners_do_not_inherit_ambient_authority"] is True
    assert summary["proof_no_runner_executes_by_default"] is True
    assert wing.runner_executed is False
    assert wing.host_mutation_performed is False
    assert any(item.runner_trust_class == "federation_import_runner" for item in wing.delegated_runner_boundaries)
