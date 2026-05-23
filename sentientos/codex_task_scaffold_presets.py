from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class CodexTaskScaffoldPreset:
    preset_id: str
    default_deliverables: tuple[str, ...]
    default_forbidden_surfaces: tuple[str, ...]
    default_integration_expectations: tuple[str, ...]
    default_validation_command_families: tuple[str, ...]
    default_final_report_items: tuple[str, ...]


_PRESETS: dict[str, CodexTaskScaffoldPreset] = {
    "developer_workflow_metadata": CodexTaskScaffoldPreset(
        preset_id="developer_workflow_metadata",
        default_deliverables=("typed_metadata_api", "deterministic_cli", "docs", "tests"),
        default_forbidden_surfaces=("runtime_authority_expansion", "provider_calls", "github_mutation", "shell_from_library"),
        default_integration_expectations=("capability_registry", "reviewer_proof_bundle", "matrix_runner", "docs"),
        default_validation_command_families=("targeted_tests", "targeted_mypy", "docs_build", "prompt_boundary", "matrix_runner_summary", "matrix_runner_output", "audit"),
        default_final_report_items=("module_api_summary", "cli_summary", "preset_ids_and_behavior", "generator_integration_behavior", "capability_proof_doc_integration", "matrix_runner_integration", "full_command_matrix_results", "unresolved_risks"),
    ),
    "metadata_attestation": CodexTaskScaffoldPreset("metadata_attestation", ("attestation_schema", "attestation_validation", "docs", "tests"), ("runtime_authority_expansion", "provider_calls", "github_mutation", "shell_from_library"), ("capability_registry", "reviewer_proof_bundle", "matrix_runner", "docs"), ("targeted_tests", "targeted_mypy", "docs_build", "audit"), ("module_api_summary", "validation_results", "attestation_scope", "unresolved_risks")),
    "metadata_digest": CodexTaskScaffoldPreset("metadata_digest", ("digest_spec", "digest_validation", "docs", "tests"), ("runtime_authority_expansion", "provider_calls", "github_mutation", "shell_from_library"), ("capability_registry", "reviewer_proof_bundle", "matrix_runner", "docs"), ("targeted_tests", "targeted_mypy", "docs_build", "audit"), ("module_api_summary", "validation_results", "digest_behavior", "unresolved_risks")),
    "metadata_index": CodexTaskScaffoldPreset("metadata_index", ("index_schema", "index_validation", "docs", "tests"), ("runtime_authority_expansion", "provider_calls", "github_mutation", "shell_from_library"), ("capability_registry", "reviewer_proof_bundle", "matrix_runner", "docs"), ("targeted_tests", "targeted_mypy", "docs_build", "audit"), ("module_api_summary", "validation_results", "index_behavior", "unresolved_risks")),
    "metadata_verification": CodexTaskScaffoldPreset("metadata_verification", ("verification_schema", "verification_rules", "docs", "tests"), ("runtime_authority_expansion", "provider_calls", "github_mutation", "shell_from_library"), ("capability_registry", "reviewer_proof_bundle", "matrix_runner", "docs"), ("targeted_tests", "targeted_mypy", "docs_build", "audit"), ("module_api_summary", "validation_results", "verification_behavior", "unresolved_risks")),
    "narrow_repair": CodexTaskScaffoldPreset("narrow_repair", ("surgical_fix", "regression_test", "docs_if_behavior_changes"), ("whole_system_scope_expansion", "runtime_authority_expansion", "provider_calls", "github_mutation"), ("docs_if_behavior_changes", "matrix_runner_if_required"), ("targeted_tests", "targeted_mypy", "audit"), ("repair_scope", "regression_result", "unresolved_risks")),
    "operator_confirmed_run": CodexTaskScaffoldPreset("operator_confirmed_run", ("operator_ack_contract", "execution_receipt", "docs", "tests"), ("autonomous_execution", "provider_calls", "github_mutation", "shell_from_library"), ("capability_registry", "reviewer_proof_bundle", "matrix_runner", "docs"), ("targeted_tests", "targeted_mypy", "docs_build", "audit"), ("operator_confirmation_summary", "validation_results", "unresolved_risks")),
    "operator_review_packet": CodexTaskScaffoldPreset("operator_review_packet", ("review_packet_schema", "deterministic_packet_builder", "docs", "tests"), ("runtime_authority_expansion", "provider_calls", "github_mutation", "shell_from_library"), ("reviewer_proof_bundle", "matrix_runner", "docs"), ("targeted_tests", "targeted_mypy", "docs_build", "audit"), ("review_packet_contents", "validation_results", "unresolved_risks")),
    "stabilization": CodexTaskScaffoldPreset("stabilization", ("fallout_fixes", "regression_coverage", "docs_if_behavior_changes"), ("new_feature_expansion", "runtime_authority_expansion", "provider_calls", "github_mutation"), ("matrix_runner", "docs_if_behavior_changes"), ("targeted_tests", "targeted_mypy", "audit", "matrix_runner_summary"), ("stabilization_scope", "validation_results", "unresolved_risks")),
}


def list_preset_ids() -> tuple[str, ...]:
    return tuple(sorted(_PRESETS))


def get_preset(preset_id: str) -> CodexTaskScaffoldPreset:
    return _PRESETS[preset_id]


def validate_preset_shape(preset: CodexTaskScaffoldPreset) -> tuple[str, ...]:
    errors: list[str] = []
    if not preset.preset_id:
        errors.append("preset_id_required")
    fields = (
        preset.default_deliverables,
        preset.default_forbidden_surfaces,
        preset.default_integration_expectations,
        preset.default_validation_command_families,
        preset.default_final_report_items,
    )
    if any(not field for field in fields):
        errors.append("all_default_groups_required")
    return tuple(errors)


def preset_catalog() -> Mapping[str, CodexTaskScaffoldPreset]:
    return dict(_PRESETS)
