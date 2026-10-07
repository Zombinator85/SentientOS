from __future__ import annotations

import hashlib
import json
import re
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
    "candidate_workspace_identity", "causal_validation_candidate_sha", "causal_validation_status",
    "causal_validation_incomplete_classification", "causal_validation_command_contract_digest",
    "causal_validation_comparison_digest",
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
        deferred_ids = set(plan.get("hosted_deferred_stage_ids", ()))
        for stage in plan.get("required_stage_ids", []):
            result = stages.get(stage)
            hosted = plan.get("hosted_validation_evidence")
            hosted_verified = (
                isinstance(hosted, Mapping)
                and hosted.get("status") == "hosted_validation_evidence_ready"
                and hosted.get("candidate_sha") == plan.get("repository_sha")
                and hosted.get("candidate_tree_sha") == plan.get("candidate_tree_sha")
                and stage in hosted.get("verified_stage_ids", ())
            )
            stage_passed = isinstance(result, Mapping) and result.get("status") == "passed"
            stage_hosted = isinstance(result, Mapping) and result.get("status") == "hosted_passed" and hosted_verified
            stage_deferred = (
                isinstance(result, Mapping) and result.get("status") == "hosted_deferred"
                and stage in deferred_ids
                and (
                    (plan.get("phase") == "pre-commit" and plan.get("overall_status") == "ready_to_commit_pending_hosted_validation")
                    or (plan.get("phase") == "post-commit" and plan.get("overall_status") == "ready_for_hosted_validation")
                )
            )
            if not (stage_passed or stage_hosted or stage_deferred):
                reasons.append(f"required_stage_not_passed:{stage}")
            if stage in deferred_ids and stage_passed:
                reasons.append(f"hosted_deferred_stage_claimed_local_pass:{stage}")
        if plan.get("overall_status") in {"ready_to_commit_pending_hosted_validation", "ready_for_hosted_validation"} and (not deferred_ids or not any(isinstance(stages.get(stage), Mapping) and stages[stage].get("status") == "hosted_deferred" for stage in deferred_ids)):
            reasons.append("hosted_deferred_status_without_deferred_stages")
        if plan.get("overall_status") == "ready_to_commit" and deferred_ids:
            reasons.append("ordinary_ready_with_hosted_deferred_stages")
        if plan.get("overall_status") == "ready_for_hosted_validation":
            if plan.get("phase") != "post-commit" or not plan.get("candidate_tree_sha"):
                reasons.append("hosted_handoff_candidate_binding_missing")
            if plan.get("hosted_validation_evidence"):
                reasons.append("hosted_handoff_claims_unrun_hosted_evidence")
        if plan.get("overall_status") == "ready_for_pr_metadata" and plan.get("phase") != "pr-metadata":
            reasons.append("pr_metadata_readiness_phase_invalid")
    causal_status = plan.get("causal_validation_status", "comparison_not_supplied")
    incomplete_classification = plan.get("causal_validation_incomplete_classification")
    causal_digest = plan.get("causal_validation_comparison_digest")
    if causal_status == "comparison_incomplete":
        if incomplete_classification not in {"paired_timeout", "unclassified"}:
            reasons.append("causal_incomplete_classification_invalid")
        if not isinstance(causal_digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", causal_digest):
            reasons.append("causal_incomplete_evidence_digest_missing")
        if incomplete_classification == "paired_timeout" and "broad_validation" not in plan.get("hosted_deferred_stage_ids", ()):
            reasons.append("paired_timeout_missing_hosted_broad_stage")
    elif causal_status in {"no_regression", "improved", "regression_detected"}:
        if not isinstance(causal_digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", causal_digest):
            reasons.append("causal_evidence_digest_missing")
    elif causal_status not in {"comparison_not_supplied", "base_evidence_invalid", "candidate_evidence_invalid", "command_contract_mismatch", "environment_not_comparable"}:
        reasons.append("causal_validation_status_unknown")
    if plan.get("overall_status") == "ready_to_commit_pending_hosted_validation" and causal_status == "comparison_incomplete" and incomplete_classification != "paired_timeout":
        reasons.append("unclassified_incomplete_cannot_authorize_hosted_commit")
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
    if post_plan.get("phase") not in {"post-commit", "pr-metadata"}: reasons.append("pr_metadata_validation_phase_invalid")
    pre_status = pre_plan.get("overall_status")
    if pre_status not in {"ready_to_commit", "ready_to_commit_pending_hosted_validation"}: reasons.append("pre_commit_validation_status_invalid")
    post_status = post_plan.get("overall_status")
    if post_status == "ready_for_hosted_validation" and post_plan.get("phase") != "post-commit":
        reasons.append("post_commit_hosted_handoff_phase_invalid")
    elif post_status == "ready_for_pr_metadata" and post_plan.get("phase") != "pr-metadata":
        reasons.append("pr_metadata_validation_phase_invalid")
    elif post_status not in {"ready_for_hosted_validation", "ready_for_pr_metadata"}:
        reasons.append("pr_metadata_validation_status_invalid")

    base_sha = workspace_binding.get("base_head_sha")
    parent_sha = commit_binding.get("parent_sha")
    head_sha = commit_binding.get("head_sha")
    if pre_plan.get("repository_sha") != base_sha: reasons.append("pre_commit_validation_repository_sha_mismatch")
    if parent_sha != base_sha: reasons.append("commit_parent_mismatch")
    if post_plan.get("repository_sha") != head_sha: reasons.append("pr_metadata_validation_repository_sha_mismatch")
    deferred = tuple(pre_plan.get("hosted_deferred_stage_ids", ()))
    if pre_status == "ready_to_commit_pending_hosted_validation":
        if not deferred:
            reasons.append("hosted_deferred_stage_list_missing")
        if pre_plan.get("causal_validation_candidate_sha") != pre_plan.get("repository_sha"):
            reasons.append("pre_commit_causal_candidate_sha_mismatch")
        if post_plan.get("causal_validation_candidate_sha") != pre_plan.get("repository_sha"):
            reasons.append("post_commit_causal_candidate_sha_mismatch")
        evidence = post_plan.get("hosted_validation_evidence")
        if post_status == "ready_for_hosted_validation":
            candidate_tree = commit_binding.get("tree_sha")
            if post_plan.get("candidate_tree_sha") != candidate_tree:
                reasons.append("hosted_handoff_candidate_tree_mismatch")
            if evidence:
                reasons.append("hosted_handoff_must_not_claim_hosted_evidence")
        elif not isinstance(evidence, Mapping) or evidence.get("candidate_sha") != head_sha or evidence.get("candidate_tree_sha") != commit_binding.get("tree_sha") or evidence.get("status") != "hosted_validation_evidence_ready":
            reasons.append("hosted_validation_evidence_missing_or_stale")
        else:
            hosted_stages = set(evidence.get("verified_stage_ids", ()))
            for stage in deferred:
                if stage not in hosted_stages:
                    reasons.append(f"hosted_validation_stage_not_verified:{stage}")
                result = post_plan.get("stage_results", {}).get(stage, {})
                if not isinstance(result, Mapping) or result.get("status") != "hosted_passed":
                    reasons.append(f"hosted_validation_stage_not_bound_in_post_plan:{stage}")
    elif deferred:
        reasons.append("unexpected_hosted_deferred_stage_lineage")
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
