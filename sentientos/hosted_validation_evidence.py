from __future__ import annotations

import re
from typing import Any, Mapping


SCHEMA_VERSION = "sentientos.hosted_validation:v2"
WORKFLOW_FILE = ".github/workflows/required-quality-gate.yml"
REQUIRED_STAGES = ("broad_validation", "strict_audits", "audit_immutability", "docs_check_deps", "docs_build")
_SHA = re.compile(r"^[0-9a-f]{40}$")


def verify_hosted_validation_evidence(
    evidence: Mapping[str, Any], *, expected_sha: str, expected_tree: str, expected_repository: str
) -> dict[str, Any]:
    """Structurally verify the required hosted audit run and exact candidate binding.

    The caller must obtain this report from the named GitHub Actions workflow's
    uploaded artifact. This function verifies its complete run identity and stage
    results; it does not fetch remote evidence or treat local stage results as hosted.
    """
    reasons: list[str] = []
    if evidence.get("schema_version") != SCHEMA_VERSION:
        reasons.append("hosted_validation_schema_invalid")
    if evidence.get("repository") != expected_repository:
        reasons.append("hosted_validation_repository_mismatch")
    if evidence.get("workflow_file") != WORKFLOW_FILE:
        reasons.append("hosted_validation_workflow_mismatch")
    try:
        if int(evidence.get("run_id", 0)) <= 0 or int(evidence.get("run_attempt", 0)) <= 0:
            reasons.append("hosted_validation_run_identity_invalid")
    except (TypeError, ValueError):
        reasons.append("hosted_validation_run_identity_invalid")
    if evidence.get("event") not in {"pull_request", "push", "merge_group", "workflow_dispatch"}:
        reasons.append("hosted_validation_event_invalid")
    if evidence.get("event") == "push" and evidence.get("ref") != "refs/heads/main":
        reasons.append("hosted_validation_push_ref_invalid")
    if evidence.get("status") != "completed":
        reasons.append("hosted_validation_incomplete")
    if evidence.get("conclusion") != "success":
        reasons.append("hosted_validation_not_successful")
    head_sha = str(evidence.get("head_sha", ""))
    if not _SHA.fullmatch(head_sha) or head_sha != expected_sha:
        reasons.append("hosted_validation_candidate_sha_mismatch")
    head_tree = str(evidence.get("head_tree", ""))
    if not _SHA.fullmatch(head_tree) or head_tree != expected_tree:
        reasons.append("hosted_validation_candidate_tree_mismatch")
    stages = evidence.get("stages")
    if not isinstance(stages, Mapping):
        reasons.append("hosted_validation_stages_missing")
    else:
        for stage in REQUIRED_STAGES:
            result = stages.get(stage)
            if not isinstance(result, Mapping) or result.get("status") != "passed" or result.get("exit_code") != 0:
                reasons.append(f"hosted_validation_stage_not_passed:{stage}")
            elif ("head_sha" in result and result.get("head_sha") != head_sha) or ("head_tree" in result and result.get("head_tree") != head_tree):
                reasons.append(f"hosted_validation_stage_revision_mismatch:{stage}")
    return {
        "status": "hosted_validation_evidence_ready" if not reasons else "hosted_validation_evidence_blocked",
        "ready": not reasons,
        "reasons": reasons,
        "repository": evidence.get("repository"),
        "workflow_file": evidence.get("workflow_file"),
        "run_id": evidence.get("run_id"),
        "run_attempt": evidence.get("run_attempt"),
        "event": evidence.get("event"),
        "candidate_sha": head_sha,
        "candidate_tree_sha": head_tree,
        "conclusion": evidence.get("conclusion"),
        "completed": evidence.get("status") == "completed",
        "verified_stage_ids": [
            stage for stage in REQUIRED_STAGES
            if isinstance(stages, Mapping)
            and isinstance(stages.get(stage), Mapping)
            and stages[stage].get("status") == "passed"
        ],
    }
