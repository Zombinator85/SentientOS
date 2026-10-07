from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from sentientos.validation_causality import (
    STATUS_IMPROVED,
    STATUS_NO_REGRESSION,
    verify_comparison,
)


VALID_PHASES = {"pre-commit", "post-commit", "pr-metadata"}
VALIDATION_PROFILES = {"solo", "exhaustive"}
_ADMINISTRATOR_UNAVAILABLE_PROOF = object()


class LandingPosture(StrEnum):
    """Monotonic landing states; incomplete evidence never becomes a cause."""

    WORKTREE_UNDER_VALIDATION = "worktree_under_validation"
    REPAIR_REQUIRED_TASK_CAUSED = "repair_required_task_caused"
    VALIDATION_FAILED = "validation_failed"
    VALIDATION_INCOMPLETE = "validation_incomplete"
    POLICY_BLOCKED = "policy_blocked"
    READY_TO_COMMIT = "ready_to_commit"
    READY_TO_COMMIT_PENDING_HOSTED_VALIDATION = "ready_to_commit_pending_hosted_validation"
    IMMUTABLE_CANDIDATE_COMMITTED = "immutable_candidate_committed"
    READY_FOR_HOSTED_VALIDATION = "ready_for_hosted_validation"
    HOSTED_VALIDATION_PENDING = "hosted_validation_pending"
    HOSTED_VALIDATION_FAILED = "hosted_validation_failed"
    HOSTED_VALIDATION_INCOMPLETE = "hosted_validation_incomplete"
    HOSTED_VALIDATION_SATISFIED = "hosted_validation_satisfied"
    READY_FOR_PR_METADATA = "ready_for_pr_metadata"


LANDING_TRANSITIONS: dict[LandingPosture, frozenset[LandingPosture]] = {
    LandingPosture.WORKTREE_UNDER_VALIDATION: frozenset({
        LandingPosture.REPAIR_REQUIRED_TASK_CAUSED, LandingPosture.VALIDATION_FAILED,
        LandingPosture.VALIDATION_INCOMPLETE, LandingPosture.POLICY_BLOCKED,
        LandingPosture.READY_TO_COMMIT, LandingPosture.READY_TO_COMMIT_PENDING_HOSTED_VALIDATION,
    }),
    LandingPosture.READY_TO_COMMIT_PENDING_HOSTED_VALIDATION: frozenset({LandingPosture.IMMUTABLE_CANDIDATE_COMMITTED}),
    LandingPosture.IMMUTABLE_CANDIDATE_COMMITTED: frozenset({LandingPosture.READY_FOR_HOSTED_VALIDATION, LandingPosture.HOSTED_VALIDATION_PENDING}),
    LandingPosture.READY_FOR_HOSTED_VALIDATION: frozenset({LandingPosture.HOSTED_VALIDATION_PENDING}),
    LandingPosture.HOSTED_VALIDATION_PENDING: frozenset({LandingPosture.HOSTED_VALIDATION_FAILED, LandingPosture.HOSTED_VALIDATION_INCOMPLETE, LandingPosture.HOSTED_VALIDATION_SATISFIED}),
    LandingPosture.HOSTED_VALIDATION_SATISFIED: frozenset({LandingPosture.READY_FOR_PR_METADATA}),
    LandingPosture.READY_TO_COMMIT: frozenset({LandingPosture.IMMUTABLE_CANDIDATE_COMMITTED, LandingPosture.READY_FOR_PR_METADATA}),
}


def validate_landing_transition(source: str, target: str) -> bool:
    try:
        return LandingPosture(target) in LANDING_TRANSITIONS.get(LandingPosture(source), frozenset())
    except ValueError:
        return False


@dataclass(frozen=True)
class CodexFinalizeLandingPolicy:
    require_focused_tests: bool = True
    require_targeted_mypy: bool = True
    require_mypy_baseline: bool = True
    require_matrix_summary: bool = False
    require_matrix_output: bool = False
    require_pr_landing_gate: bool = True
    require_landing_supervisor: bool = True
    require_docs_build: bool = False
    require_prompt_boundary: bool = True
    require_strict_audits: bool = True
    require_audit_immutability: bool = True
    require_clean_working_tree: bool = True
    allow_docs_bootstrap: bool = False
    allow_strict_audit_repair: bool = False
    allow_generated_artifact_cleanup: bool = False
    allow_stale_evidence_refresh: bool = False
    require_operator_supplied_task_commands: bool = True
    require_causal_validation: bool = False
    hosted_deferrable_stage_ids: tuple[str, ...] = ("strict_audits", "audit_immutability", "docs_check_deps", "docs_build", "broad_validation")


@dataclass(frozen=True)
class CodexFinalizeLandingRequest:
    title: str
    intended_commit_title: str
    matrix_json_path: str
    phase: str = "pr-metadata"
    focused_test_commands: tuple[str, ...] = ()
    targeted_mypy_commands: tuple[str, ...] = ()
    extra_required_commands: tuple[str, ...] = ()
    changed_files: tuple[str, ...] = ()
    inferred_changed_files: tuple[str, ...] = ()
    inferred_tracked_changed_files: tuple[str, ...] = ()
    inferred_untracked_task_files: tuple[str, ...] = ()
    allow_current_tracked_changes: bool = False
    allow_current_task_files: bool = False
    dirty_file_classification_source: str = "declared"
    allow_no_focused_tests: bool = False
    workspace_root: str = "."
    summary: bool = False
    repository_sha: str = ""
    hosted_validation_evidence: Mapping[str, Any] | None = None
    deferred_stage_ids: tuple[str, ...] = ()
    immutable_base_sha: str = ""
    candidate_workspace_identity: str = ""
    causal_validation_evidence: Mapping[str, Any] | None = None
    causal_validation_expected_command_digest: str = ""
    task_acceptance_status: str = "not_supplied"
    protected_corridor_status: str = "not_required"
    require_causal_validation: bool = False
    hosted_validation_handoff_authorized: bool = False
    candidate_tree_sha: str = ""
    causal_validation_candidate_sha: str = ""


@dataclass(frozen=True)
class CodexFinalizeLandingCommandResult:
    stage: str
    command: str
    exit_code: int
    output_tail: str = ""
    required: bool = True
    availability_status: str = "available"
    availability_evidence: Mapping[str, Any] | None = None
    availability_proof: object | None = field(default=None, repr=False, compare=False)
    command_contract_digest: str = ""


@dataclass(frozen=True)
class CodexFinalizeLandingArtifactFinding:
    path: str
    classification: str
    action: str


@dataclass(frozen=True)
class CodexFinalizeLandingDecision:
    status: str
    reasons: tuple[str, ...]
    deferred_stage_ids: tuple[str, ...] = ()
    deferred_stage_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class CodexFinalizeLandingReport:
    commands: tuple[CodexFinalizeLandingCommandResult, ...]
    artifacts: tuple[CodexFinalizeLandingArtifactFinding, ...]
    hosted_validation_evidence: Mapping[str, Any] | None = None
    assessments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CodexFinalizeLandingResult:
    policy: CodexFinalizeLandingPolicy
    decision: CodexFinalizeLandingDecision
    report: CodexFinalizeLandingReport

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for command in payload.get("report", {}).get("commands", []):
            command.pop("availability_proof", None)
        return payload


@dataclass(frozen=True)
class CodexFinalizeLandingEvidenceFreshness:
    stale_evidence_reasons: tuple[str, ...] = ()
    stale_evidence_refresh_attempted: bool = False
    stale_evidence_refresh_result: str = "not_required"
    refreshed_matrix_json_path: str | None = None


def _normalize_phase(phase: str) -> str:
    normalized = phase.replace("_", "-")
    if normalized not in VALID_PHASES:
        return ""
    return normalized


def evaluate_finalize_landing(
    request: CodexFinalizeLandingRequest,
    command_results: tuple[CodexFinalizeLandingCommandResult, ...],
    artifact_findings: tuple[CodexFinalizeLandingArtifactFinding, ...],
    policy: CodexFinalizeLandingPolicy | None = None,
) -> CodexFinalizeLandingResult:
    pol = policy or CodexFinalizeLandingPolicy()
    reasons: list[str] = []
    phase = _normalize_phase(request.phase)

    if not phase:
        reasons.append("invalid_phase")

    if request.title != request.intended_commit_title:
        reasons.append("title_mismatch")
    if pol.require_focused_tests and not request.focused_test_commands and not request.allow_no_focused_tests:
        reasons.append("focused_tests_missing")

    causal_assessment: dict[str, Any] = {"status": "comparison_not_supplied", "reasons": []}
    if request.causal_validation_evidence is not None:
        causal_assessment = verify_comparison(
            request.causal_validation_evidence,
            immutable_base_sha=request.immutable_base_sha,
            candidate_sha=request.causal_validation_candidate_sha or request.repository_sha,
            candidate_workspace_identity=request.candidate_workspace_identity,
            expected_command_contract_digest=request.causal_validation_expected_command_digest or None,
        )
    causal_ready = causal_assessment.get("status") in {STATUS_NO_REGRESSION, STATUS_IMPROVED}
    paired_timeout = (
        causal_assessment.get("status") == "comparison_incomplete"
        and causal_assessment.get("incomplete_classification") == "paired_timeout"
    )
    if (pol.require_causal_validation or request.require_causal_validation) and request.causal_validation_evidence is None:
        reasons.append("validation_incomplete:causal_validation_evidence_missing")
    elif request.causal_validation_evidence is not None and not causal_ready and not paired_timeout:
        if causal_assessment.get("status") == "regression_detected":
            reasons.append("candidate_regression_detected")
        elif causal_assessment.get("status") == "comparison_incomplete":
            reasons.append("validation_incomplete:causal_comparison")
        else:
            reasons.append("policy_blocked:causal_evidence_invalid_or_incomparable")
    if request.task_acceptance_status not in {"not_supplied", "task_acceptance_ready"}:
        reasons.append("validation_failed:task_acceptance_not_ready")
    if request.protected_corridor_status in {"regression_detected", "blocking_failure", "failed"}:
        reasons.append("protected_corridor_regression_detected")
    elif request.protected_corridor_status not in {"not_required", "not_applicable", "passed", "green", "amber"}:
        reasons.append("protected_corridor_status_incomplete")

    deferred: list[str] = []
    deferred_reasons: list[str] = []
    hosted = request.hosted_validation_evidence or {}
    hosted_ready = (
        hosted.get("status") == "hosted_validation_evidence_ready"
        and hosted.get("candidate_sha") == request.repository_sha
        and hosted.get("candidate_tree_sha") == request.candidate_tree_sha
        and set(hosted.get("verified_stage_ids", ())) >= set(request.deferred_stage_ids)
    )
    hosted_handoff_pending = (
        phase == "post-commit" and request.hosted_validation_handoff_authorized
        and bool(request.deferred_stage_ids) and not request.hosted_validation_evidence
        and bool(request.candidate_tree_sha)
    )
    if phase in {"post-commit", "pr-metadata"} and request.deferred_stage_ids and not hosted_ready and not hosted_handoff_pending:
        reasons.append("hosted_validation_evidence_missing_or_unbound")
    command_stage_ids = {result.stage for result in command_results}
    if (pol.require_causal_validation or request.require_causal_validation) and "broad_validation" not in command_stage_ids:
        reasons.append("validation_incomplete:broad_validation_evidence_missing")
    if phase in {"post-commit", "pr-metadata"}:
        for stage in request.deferred_stage_ids:
            if stage not in command_stage_ids:
                reasons.append(f"deferred_stage_missing_from_post_commit_validation:{stage}")
    for result in command_results:
        if result.required and result.exit_code != 0:
            if (
                result.stage == "broad_validation"
                and causal_ready
                and result.command_contract_digest
                and result.command_contract_digest == causal_assessment.get("command_contract_digest")
            ):
                # The raw exit remains in the report. Only causal task-regression is
                # non-blocking here; repository health stays independently visible.
                continue
            if (
                result.stage == "broad_validation" and paired_timeout
                and result.exit_code == 124
                and result.command_contract_digest
                and result.command_contract_digest == causal_assessment.get("command_contract_digest")
                and phase in {"pre-commit", "post-commit"}
                and result.stage in pol.hosted_deferrable_stage_ids
                and (phase == "pre-commit" or result.stage in request.deferred_stage_ids)
                and (phase == "pre-commit" or hosted_handoff_pending or hosted_ready)
            ):
                if phase == "pre-commit":
                    deferred.append("broad_validation")
                    deferred_reasons.append("broad_validation:paired_base_candidate_timeout_requires_hosted_validation")
                continue
            evidence = result.availability_evidence or {}
            unavailable_proven = (
                result.availability_status == "substrate_unavailable"
                and result.availability_proof is _ADMINISTRATOR_UNAVAILABLE_PROOF
                and evidence.get("probe") == "administrator_capability"
                and evidence.get("available") is False
                and evidence.get("source") == "sentientos.admin_utils.is_admin"
            )
            if unavailable_proven and result.stage in pol.hosted_deferrable_stage_ids:
                if phase == "pre-commit":
                    deferred.append(result.stage)
                    deferred_reasons.append(f"{result.stage}:administrator_capability_unavailable")
                elif phase in {"post-commit", "pr-metadata"} and result.stage in request.deferred_stage_ids and hosted_ready and result.stage in hosted.get("verified_stage_ids", ()):
                    continue
                elif phase == "post-commit" and result.stage in request.deferred_stage_ids and hosted_handoff_pending:
                    continue
                else:
                    reasons.append(f"validation_incomplete:stage_unavailable_without_bound_hosted_evidence:{result.stage}")
            elif unavailable_proven:
                reasons.append(f"validation_incomplete:stage_unavailable_without_hosted_substitute:{result.stage}")
            else:
                if result.stage == "broad_validation" and causal_assessment.get("status") == "comparison_incomplete":
                    reasons.append("validation_incomplete:broad_validation")
                else:
                    reasons.append(f"validation_failed:stage_failed:{result.stage}")

    changed_file_set = set(request.changed_files) | set(request.inferred_changed_files) | set(request.inferred_tracked_changed_files) | set(request.inferred_untracked_task_files)
    found_source_not_declared = False
    found_unknown = False
    found_generated = False
    found_intended = False
    for artifact in artifact_findings:
        if artifact.classification == "unknown_dirty_file":
            found_unknown = True
        elif artifact.classification == "source_change_not_declared":
            found_source_not_declared = True
        elif artifact.classification == "generated_runtime_artifact":
            found_generated = True
        elif artifact.classification == "intended_task_change":
            found_intended = True
            if artifact.path not in changed_file_set and phase == "pre-commit":
                found_source_not_declared = True

    if found_unknown:
        reasons.append("unknown_dirty_tree")
    if found_source_not_declared:
        reasons.append("source_change_not_declared")
    if found_generated and not pol.allow_generated_artifact_cleanup:
        reasons.append("generated_artifacts_present")
    if phase in {"post-commit", "pr-metadata"} and found_intended:
        reasons.append("source_dirty_tree_post_commit")

    if reasons:
        if "invalid_phase" in reasons:
            status = "manual_review_required"
        elif "unknown_dirty_tree" in reasons:
            status = "manual_review_required"
        elif "candidate_regression_detected" in reasons:
            status = LandingPosture.REPAIR_REQUIRED_TASK_CAUSED.value
        elif any(reason.startswith(("hosted_validation_", "deferred_stage_missing_from_post_commit_validation:")) for reason in reasons):
            hosted_failed = hosted.get("conclusion") == "failure" or any(
                str(reason).startswith("hosted_validation_stage_not_passed:") for reason in hosted.get("reasons", ())
            )
            status = LandingPosture.HOSTED_VALIDATION_FAILED.value if hosted_failed else LandingPosture.HOSTED_VALIDATION_INCOMPLETE.value
        elif any(reason.startswith("validation_incomplete:") for reason in reasons):
            status = LandingPosture.VALIDATION_INCOMPLETE.value
        elif any(reason.startswith("validation_failed:") for reason in reasons):
            status = LandingPosture.VALIDATION_FAILED.value
        elif any(reason.startswith("policy_blocked:") for reason in reasons):
            status = LandingPosture.POLICY_BLOCKED.value
        else:
            status = LandingPosture.POLICY_BLOCKED.value
        return CodexFinalizeLandingResult(pol, CodexFinalizeLandingDecision(status, tuple(reasons), tuple(deferred), tuple(deferred_reasons)), CodexFinalizeLandingReport(command_results, artifact_findings, request.hosted_validation_evidence, {
            "task_acceptance_status": request.task_acceptance_status,
            "regression_gate_status": causal_assessment.get("status", "comparison_not_supplied"),
            "protected_corridor_status": request.protected_corridor_status,
            "repository_health_status": causal_assessment.get("repository_health_status", "unknown"),
            "environment_deferred_stage_ids": list(deferred),
            "hosted_evidence_status": hosted.get("status", "not_supplied"),
        }))

    ready_status = (
        LandingPosture.READY_TO_COMMIT_PENDING_HOSTED_VALIDATION.value
        if phase == "pre-commit" and deferred
        else LandingPosture.READY_TO_COMMIT.value
        if phase == "pre-commit"
        else LandingPosture.READY_FOR_HOSTED_VALIDATION.value
        if phase == "post-commit" and hosted_handoff_pending
        else LandingPosture.READY_FOR_PR_METADATA.value
    )
    return CodexFinalizeLandingResult(pol, CodexFinalizeLandingDecision(ready_status, (), tuple(deferred), tuple(deferred_reasons)), CodexFinalizeLandingReport(command_results, artifact_findings, request.hosted_validation_evidence, {
        "task_acceptance_status": request.task_acceptance_status,
        "regression_gate_status": causal_assessment.get("status", "comparison_not_supplied"),
        "protected_corridor_status": request.protected_corridor_status,
        "repository_health_status": causal_assessment.get("repository_health_status", "unknown"),
        "environment_deferred_stage_ids": list(deferred),
        "hosted_evidence_status": hosted.get("status", "not_supplied"),
    }))
