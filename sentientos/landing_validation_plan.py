from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


SCHEMA_VERSION = "sentientos.landing_validation_plan:v1"
VALIDATION_PROFILES = ("solo", "exhaustive")
SOLO_MATRIX_STATUS = "not_requested_for_solo_profile"
EXHAUSTIVE_MATRIX_STATUSES = {
    "matrix_passed", "matrix_failed", "matrix_timed_out", "matrix_resumed", "matrix_reused",
}
STABLE_LINEAGE_FIELDS = (
    "requested_profile", "effective_profile", "title", "intended_commit_title",
    "task_acceptance_manifest_digest", "task_acceptance_provenance_digest",
    "focused_test_command_contract", "targeted_mypy_command_contract",
)


def canonical_digest(payload: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "artifact_digest"}
    encoded = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def seal_validation_plan(payload: Mapping[str, Any]) -> dict[str, Any]:
    plan = dict(payload)
    plan["schema_version"] = SCHEMA_VERSION
    plan["artifact_digest"] = canonical_digest(plan)
    return plan


def verify_validation_plan(plan: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if plan.get("schema_version") != SCHEMA_VERSION:
        reasons.append("validation_plan_schema_invalid")
    requested = str(plan.get("requested_profile", ""))
    effective = str(plan.get("effective_profile", ""))
    if requested not in VALIDATION_PROFILES or effective != requested:
        reasons.append("validation_profile_invalid_or_mutated")
    matrix_status = str(plan.get("exhaustive_matrix_status", ""))
    if effective == "solo" and matrix_status != SOLO_MATRIX_STATUS:
        reasons.append("solo_matrix_status_inconsistent")
    if effective == "exhaustive" and matrix_status not in EXHAUSTIVE_MATRIX_STATUSES:
        reasons.append("exhaustive_matrix_status_inconsistent")
    stages = plan.get("stage_results", {})
    if not isinstance(stages, Mapping):
        reasons.append("validation_stage_results_invalid")
    else:
        for stage in plan.get("required_stage_ids", []):
            result = stages.get(stage)
            if not isinstance(result, Mapping) or result.get("status") != "passed":
                reasons.append(f"required_stage_not_passed:{stage}")
    if plan.get("artifact_digest") != canonical_digest(plan):
        reasons.append("validation_plan_digest_mismatch")
    return not reasons, tuple(reasons)


def verify_validation_plan_transition(
    pre_plan: Mapping[str, Any], post_plan: Mapping[str, Any],
    workspace_binding: Mapping[str, Any], commit_binding: Mapping[str, Any],
) -> tuple[bool, tuple[str, ...], dict[str, Any]]:
    """Verify two phase-local plans as one exact landing validation lineage."""
    reasons: list[str] = []
    pre_valid, pre_reasons = verify_validation_plan(pre_plan)
    post_valid, post_reasons = verify_validation_plan(post_plan)
    if not pre_valid:
        reasons.extend(f"pre_commit_validation_plan_invalid:{reason}" for reason in pre_reasons)
    if not post_valid:
        reasons.extend(f"pr_metadata_validation_plan_invalid:{reason}" for reason in post_reasons)
    for field in STABLE_LINEAGE_FIELDS:
        if pre_plan.get(field) != post_plan.get(field):
            reasons.append(f"validation_lineage_field_mismatch:{field}")
    if pre_plan.get("phase") != "pre-commit": reasons.append("pre_commit_validation_phase_invalid")
    if post_plan.get("phase") != "pr-metadata": reasons.append("pr_metadata_validation_phase_invalid")
    if pre_plan.get("overall_status") != "ready_to_commit": reasons.append("pre_commit_validation_status_invalid")
    if post_plan.get("overall_status") != "ready_for_pr_metadata": reasons.append("pr_metadata_validation_status_invalid")

    base_sha = workspace_binding.get("base_head_sha")
    parent_sha = commit_binding.get("parent_sha")
    head_sha = commit_binding.get("head_sha")
    if pre_plan.get("repository_sha") != base_sha: reasons.append("pre_commit_validation_repository_sha_mismatch")
    if parent_sha != base_sha: reasons.append("commit_parent_mismatch")
    if post_plan.get("repository_sha") != head_sha: reasons.append("pr_metadata_validation_repository_sha_mismatch")
    if commit_binding.get("commit_subject") != workspace_binding.get("intended_commit_title"):
        reasons.append("commit_title_mismatch")
    if commit_binding.get("changed_path_manifest_digest") != workspace_binding.get("changed_path_manifest_digest"):
        reasons.append("workspace_manifest_mismatch")

    matrix_digest = workspace_binding.get("matrix_digest")
    if commit_binding.get("matrix_digest") != matrix_digest: reasons.append("matrix_digest_mismatch")
    profile = pre_plan.get("effective_profile")
    if profile == "exhaustive":
        if pre_plan.get("exhaustive_matrix_status") not in {"matrix_passed", "matrix_reused"}:
            reasons.append("pre_commit_matrix_lineage_unverified")
        if post_plan.get("exhaustive_matrix_status") != "matrix_reused":
            reasons.append("pr_metadata_matrix_lineage_not_reused")
        if pre_plan.get("exhaustive_matrix_digest") not in {None, "", matrix_digest}:
            reasons.append("pre_commit_matrix_digest_mismatch")
        if post_plan.get("exhaustive_matrix_digest") not in {None, "", matrix_digest}:
            reasons.append("pr_metadata_matrix_digest_mismatch")

    stable_projection = {field: pre_plan.get(field) for field in STABLE_LINEAGE_FIELDS}
    proof = {
        "transition_status": "validation_plan_transition_ready" if not reasons else "validation_plan_transition_blocked",
        "pre_plan_digest": pre_plan.get("artifact_digest"), "post_plan_digest": post_plan.get("artifact_digest"),
        "shared_validation_profile": profile, "stable_lineage_digest": canonical_digest(stable_projection),
        "pre_phase": pre_plan.get("phase"), "post_phase": post_plan.get("phase"),
        "pre_repository_sha": pre_plan.get("repository_sha"), "post_repository_sha": post_plan.get("repository_sha"),
        "commit_parent_sha": parent_sha, "commit_head_sha": head_sha, "matrix_digest": matrix_digest,
    }
    return not reasons, tuple(reasons), proof
