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
ACCEPTANCE_DIGEST_FIELDS = frozenset({
    "task_acceptance_manifest_digest",
    "task_acceptance_provenance_digest",
})


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


def _verify_acceptance_source_rollforward(
    pre_plan: Mapping[str, Any], post_plan: Mapping[str, Any],
    workspace_binding: Mapping[str, Any], commit_binding: Mapping[str, Any],
    pre_acceptance: Mapping[str, Any] | None,
    post_acceptance: Mapping[str, Any] | None,
) -> tuple[bool, tuple[str, ...], dict[str, Any]]:
    """Permit only verified task-acceptance evidence to advance from parent to commit SHA."""
    reasons: list[str] = []
    proof: dict[str, Any] = {
        "status": "blocked",
        "pre_repository_sha": pre_acceptance.get("repository_sha") if pre_acceptance else None,
        "post_repository_sha": post_acceptance.get("repository_sha") if post_acceptance else None,
        "required_node_ids": [],
        "reasons": reasons,
    }
    if pre_acceptance is None or post_acceptance is None:
        reasons.append("task_acceptance_rollforward_evidence_missing")
        return False, tuple(reasons), proof
    if pre_acceptance.get("status") != "task_acceptance_ready":
        reasons.append("pre_commit_task_acceptance_not_ready")
    if post_acceptance.get("status") != "task_acceptance_ready":
        reasons.append("pr_metadata_task_acceptance_not_ready")
    base_sha = workspace_binding.get("base_head_sha")
    head_sha = commit_binding.get("head_sha")
    if pre_acceptance.get("repository_sha") != base_sha:
        reasons.append("pre_commit_task_acceptance_source_sha_mismatch")
    if post_acceptance.get("repository_sha") != head_sha:
        reasons.append("pr_metadata_task_acceptance_source_sha_mismatch")
    if pre_acceptance.get("task_classification") != post_acceptance.get("task_classification"):
        reasons.append("task_acceptance_classification_changed")
    for plan, acceptance, label in (
        (pre_plan, pre_acceptance, "pre_commit"),
        (post_plan, post_acceptance, "pr_metadata"),
    ):
        if plan.get("task_acceptance_manifest_digest") != acceptance.get("manifest_digest"):
            reasons.append(f"{label}_task_acceptance_manifest_digest_mismatch")
        if plan.get("task_acceptance_provenance_digest") != acceptance.get("provenance_digest"):
            reasons.append(f"{label}_task_acceptance_provenance_digest_mismatch")
    pre_required = pre_acceptance.get("required_node_ids")
    post_required = post_acceptance.get("required_node_ids")
    pre_successful = pre_acceptance.get("successful_path_node_ids")
    post_successful = post_acceptance.get("successful_path_node_ids")
    required_nodes = pre_required if isinstance(pre_required, list) else []
    successful_nodes = pre_successful if isinstance(pre_successful, list) else []
    valid_required = (
        bool(required_nodes)
        and all(isinstance(node, str) and node for node in required_nodes)
        and len(set(required_nodes)) == len(required_nodes)
        and required_nodes == post_required
    )
    if not valid_required:
        reasons.append("task_acceptance_required_nodes_changed")
    valid_successful = (
        bool(successful_nodes)
        and all(isinstance(node, str) and node for node in successful_nodes)
        and len(set(successful_nodes)) == len(successful_nodes)
        and successful_nodes == post_successful
        and valid_required
        and set(successful_nodes).issubset(set(required_nodes))
    )
    if not valid_successful:
        reasons.append("task_acceptance_successful_path_changed")
    else:
        proof["required_node_ids"] = list(required_nodes)
        for acceptance, label in (
            (pre_acceptance, "pre_commit"),
            (post_acceptance, "pr_metadata"),
        ):
            outcomes = acceptance.get("node_outcomes")
            outcome_map = {
                str(item.get("node_id")): item
                for item in outcomes if isinstance(item, Mapping)
            } if isinstance(outcomes, list) else {}
            for node_id in required_nodes:
                outcome = outcome_map.get(node_id)
                if not isinstance(outcome, Mapping) or not (
                    outcome.get("exists") is True
                    and outcome.get("selected") is True
                    and outcome.get("phase") == "call"
                    and outcome.get("outcome") == "passed"
                    and outcome.get("passed") is True
                ):
                    reasons.append(f"{label}_task_acceptance_node_not_passed:{node_id}")
    for acceptance, label in (
        (pre_acceptance, "pre_commit"),
        (post_acceptance, "pr_metadata"),
    ):
        required_witnesses = acceptance.get("required_witness_contract_count")
        passed_witnesses = acceptance.get("passed_witness_contract_count")
        contracts = acceptance.get("witness_contract_results")
        if (acceptance.get("witness_status") != "ready"
                or not isinstance(required_witnesses, int)
                or isinstance(required_witnesses, bool)
                or not isinstance(passed_witnesses, int)
                or isinstance(passed_witnesses, bool)
                or required_witnesses != passed_witnesses
                or not isinstance(contracts, list)
                or required_witnesses != len(contracts)
                or any(not isinstance(item, Mapping) or item.get("passed") is not True
                       or not isinstance(item.get("node_id"), str)
                       or not isinstance(item.get("contract_id"), str)
                       for item in contracts)):
            reasons.append(f"{label}_task_acceptance_witnesses_not_ready")
    pre_contracts = pre_acceptance.get("witness_contract_results")
    post_contracts = post_acceptance.get("witness_contract_results")
    if isinstance(pre_contracts, list) and isinstance(post_contracts, list):
        pre_identity = sorted(
            (str(item.get("node_id", "")), str(item.get("contract_id", "")), item.get("passed"))
            for item in pre_contracts if isinstance(item, Mapping)
        )
        post_identity = sorted(
            (str(item.get("node_id", "")), str(item.get("contract_id", "")), item.get("passed"))
            for item in post_contracts if isinstance(item, Mapping)
        )
        if pre_identity != post_identity:
            reasons.append("task_acceptance_witness_contracts_changed")
    if not reasons:
        proof["status"] = "source_sha_rollforward_ready"
    return not reasons, tuple(reasons), proof


def verify_validation_plan_transition(
    pre_plan: Mapping[str, Any], post_plan: Mapping[str, Any],
    workspace_binding: Mapping[str, Any], commit_binding: Mapping[str, Any],
    *, pre_acceptance: Mapping[str, Any] | None = None,
    post_acceptance: Mapping[str, Any] | None = None,
) -> tuple[bool, tuple[str, ...], dict[str, Any]]:
    """Verify two phase-local plans as one exact landing validation lineage."""
    reasons: list[str] = []
    pre_valid, pre_reasons = verify_validation_plan(pre_plan)
    post_valid, post_reasons = verify_validation_plan(post_plan)
    if not pre_valid:
        reasons.extend(f"pre_commit_validation_plan_invalid:{reason}" for reason in pre_reasons)
    if not post_valid:
        reasons.extend(f"pr_metadata_validation_plan_invalid:{reason}" for reason in post_reasons)
    acceptance_digest_mismatches: list[str] = []
    for field in STABLE_LINEAGE_FIELDS:
        if pre_plan.get(field) != post_plan.get(field):
            if field in ACCEPTANCE_DIGEST_FIELDS:
                acceptance_digest_mismatches.append(field)
                continue
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
    acceptance_transition: dict[str, Any] = {
        "status": "same_evidence",
        "pre_repository_sha": pre_acceptance.get("repository_sha") if pre_acceptance else None,
        "post_repository_sha": post_acceptance.get("repository_sha") if post_acceptance else None,
        "required_node_ids": [],
        "reasons": [],
    }
    if acceptance_digest_mismatches:
        acceptance_ready, acceptance_reasons, acceptance_transition = _verify_acceptance_source_rollforward(
            pre_plan, post_plan, workspace_binding, commit_binding,
            pre_acceptance, post_acceptance,
        )
        acceptance_transition["reasons"] = list(acceptance_reasons)
        if acceptance_ready:
            acceptance_transition["status"] = "source_sha_rollforward_ready"
        else:
            reasons.extend(f"validation_lineage_field_mismatch:{field}" for field in acceptance_digest_mismatches)
            reasons.extend(acceptance_reasons)
    elif (pre_acceptance is not None and post_acceptance is not None
          and pre_acceptance.get("repository_sha") != post_acceptance.get("repository_sha")):
        reasons.append("task_acceptance_source_sha_changed_without_digest_transition")
        acceptance_transition["status"] = "blocked"
        acceptance_transition["reasons"] = ["task_acceptance_source_sha_changed_without_digest_transition"]
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
        "task_acceptance_transition": acceptance_transition,
    }
    return not reasons, tuple(reasons), proof
