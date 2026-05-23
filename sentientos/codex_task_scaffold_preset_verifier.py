from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sentientos.codex_task_scaffold import CodexTaskScaffoldRequest, build_codex_task_scaffold
from sentientos.codex_task_scaffold_presets import get_preset, list_preset_ids, preset_catalog, validate_preset_shape

REQUIRED_PRESET_IDS: tuple[str, ...] = (
    "developer_workflow_metadata",
    "metadata_attestation",
    "metadata_digest",
    "metadata_index",
    "metadata_verification",
    "narrow_repair",
    "operator_confirmed_run",
    "operator_review_packet",
    "stabilization",
)
WHOLE_SYSTEM_PRESETS: tuple[str, ...] = tuple(pid for pid in REQUIRED_PRESET_IDS if pid != "narrow_repair")
FORBIDDEN_AUTHORITY_MARKERS: tuple[str, ...] = (
    "provider",
    "network",
    "github",
    "subprocess",
    "action-wing",
)
REQUIRED_FINAL_REPORT_ITEMS: tuple[str, ...] = (
    "full_command_matrix_results",
    "unresolved_risks",
)
REQUIRED_VALIDATION_FAMILIES: tuple[str, ...] = (
    "targeted_tests",
    "targeted_mypy",
    "audit",
)


@dataclass(frozen=True)
class CodexTaskScaffoldPresetVerifierResult:
    status: str
    checked_preset_ids: tuple[str, ...]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _verify_preset(preset_id: str, errors: list[str]) -> None:
    preset = get_preset(preset_id)
    shape_errors = validate_preset_shape(preset)
    errors.extend(f"{preset_id}:shape:{err}" for err in shape_errors)


    if not all(
        (
            preset.default_deliverables,
            preset.default_forbidden_surfaces,
            preset.default_integration_expectations,
            preset.default_validation_command_families,
            preset.default_final_report_items,
        )
    ):
        errors.append(f"{preset_id}:missing_required_groups")

    for family in REQUIRED_VALIDATION_FAMILIES:
        if family not in preset.default_validation_command_families:
            errors.append(f"{preset_id}:missing_validation_family:{family}")

    for item in REQUIRED_FINAL_REPORT_ITEMS:
        if item not in preset.default_final_report_items:
            errors.append(f"{preset_id}:missing_final_report_item:{item}")

    if preset_id in WHOLE_SYSTEM_PRESETS and "full_command_matrix_results" not in preset.default_final_report_items:
        errors.append(f"{preset_id}:whole_system_missing_final_matrix_expectation")

    if preset_id == "narrow_repair":
        if "whole_system_scope_expansion" not in preset.default_forbidden_surfaces:
            errors.append("narrow_repair:missing_exceptional_scope_boundary")
        if "surgical_fix" not in preset.default_deliverables:
            errors.append("narrow_repair:missing_surgical_fix_deliverable")

    authority_text = " ".join(
        preset.default_deliverables
        + preset.default_forbidden_surfaces
        + preset.default_integration_expectations
        + preset.default_validation_command_families
        + preset.default_final_report_items
    ).lower()
    for marker in FORBIDDEN_AUTHORITY_MARKERS:
        if marker == "github":
            continue
        if marker in authority_text:
            errors.append(f"{preset_id}:forbidden_authority_marker_present:{marker}")


def _verify_generated_scaffold(preset_id: str, errors: list[str]) -> None:
    request = CodexTaskScaffoldRequest(
        task_name="preset-verifier-contract",
        task_goal="verify preset behavior",
        subsystem_kind=preset_id,
        prompt_mode="narrow_repair" if preset_id == "narrow_repair" else "whole_system",
        commit_title="[codex:developer] verify scaffold preset",
    )
    scaffold = build_codex_task_scaffold(request).scaffold
    prompt = scaffold.generated_prompt
    if preset_id != "narrow_repair":
        required_clauses = (
            "Whole-System Codex Operating Doctrine",
            "Critical landing rule",
            "Do not create PR metadata before green final validation.",
        )
        for clause in required_clauses:
            if clause not in prompt:
                errors.append(f"{preset_id}:generated_scaffold_missing_clause:{clause}")
    if not scaffold.commit_pr_title.startswith("[codex:"):
        errors.append(f"{preset_id}:generated_scaffold_bad_title_discipline")


def verify_codex_task_scaffold_presets(preset_id: str | None = None) -> CodexTaskScaffoldPresetVerifierResult:
    errors: list[str] = []
    catalog_ids = list_preset_ids()
    if tuple(catalog_ids) != tuple(sorted(catalog_ids)):
        errors.append("catalog_ids_not_sorted")

    required_missing = tuple(pid for pid in REQUIRED_PRESET_IDS if pid not in catalog_ids)
    if required_missing:
        errors.extend(f"missing_required_preset:{pid}" for pid in required_missing)

    catalog = preset_catalog()
    if tuple(sorted(catalog)) != tuple(catalog_ids):
        errors.append("catalog_json_not_deterministic")

    target_ids = (preset_id,) if preset_id else tuple(catalog_ids)
    for pid in target_ids:
        if pid not in catalog_ids:
            errors.append(f"unknown_preset_id:{pid}")
            continue
        _verify_preset(pid, errors)
        _verify_generated_scaffold(pid, errors)

    status = "codex_task_scaffold_preset_verifier_ready" if not errors else "codex_task_scaffold_preset_verifier_incomplete"
    return CodexTaskScaffoldPresetVerifierResult(status=status, checked_preset_ids=tuple(target_ids), errors=tuple(sorted(set(errors))))
