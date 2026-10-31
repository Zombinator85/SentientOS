from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


VALID_PHASES = {"pre-commit", "post-commit", "pr-metadata"}
VALIDATION_PROFILES = {"solo", "exhaustive"}
HOSTED_REQUIRED_STAGES = ("strict_audits", "audit_immutability")
HOSTED_QUALITY_GATE_CONTEXT = "Required / Quality Gate"
HOSTED_QUALITY_GATE_INTEGRATION_ID = 15368


def _environment_precondition_reason(result: CodexFinalizeLandingCommandResult) -> str | None:
    """Name known runtime preconditions without treating their failure as success."""
    output = result.output_tail
    lowered_output = output.lower()
    sandbox_access_denial = (
        "sandbox" in lowered_output
        and any(marker in lowered_output for marker in ("permission denied", "operation not permitted"))
    )
    if sandbox_access_denial:
        return f"environment_precondition_unavailable:{result.stage}:sandbox_policy_restriction"
    if result.stage == "focused_tests" and (
        "run_tests dependency bootstrap failed" in output
        or "minimal-test-airlock-install-failed" in output
    ):
        return "environment_precondition_unavailable:focused_tests:python_dependency_bootstrap_failed"
    if (
        result.stage == "focused_tests"
        and "SSLCertVerificationError" in output
        and any(marker in output.lower() for marker in ("pip", "dependency", "bootstrap"))
    ):
        return "environment_precondition_unavailable:focused_tests:package_bootstrap_tls_trust"
    if result.stage == "mypy_baseline" and "mypy_baseline_toolchain_mismatch" in output:
        return "environment_precondition_unavailable:mypy_baseline:pinned_toolchain_missing_or_mismatched"
    if result.stage == "audit_immutability" and "ModuleNotFoundError: No module named 'nacl'" in output:
        return "environment_precondition_unavailable:audit_immutability:pynacl_missing"
    if result.stage in {"docs_check_deps", "docs_build"} and "Docs build dependencies missing." in output:
        return f"environment_precondition_unavailable:{result.stage}:docs_dependencies_missing"
    if "temporary-storage-unavailable" in output:
        return f"environment_precondition_unavailable:{result.stage}:temporary_storage"
    return None


def _authority_denial_reason(result: CodexFinalizeLandingCommandResult) -> str | None:
    """Identify explicit privilege denials so workflow recovery cannot retry them."""
    output = result.output_tail.lower()
    if result.stage == "strict_audits" and "access denied: run as administrator" in output:
        return "authority_denied:strict_audits:administrator_required"
    if (
        "sandbox" in output
        and any(marker in output for marker in ("permission denied", "operation not permitted"))
    ):
        return None
    if "permission denied" in output or "operation not permitted" in output:
        return f"authority_denied:{result.stage}:explicit_access_denial"
    return None


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
    defer_privileged_checks_to_hosted: bool = False
    allow_no_focused_tests: bool = False
    workspace_root: str = "."
    summary: bool = False


@dataclass(frozen=True)
class CodexFinalizeLandingCommandResult:
    stage: str
    command: str
    exit_code: int | None
    output_tail: str = ""
    required: bool = True


@dataclass(frozen=True)
class CodexFinalizeLandingArtifactFinding:
    path: str
    classification: str
    action: str


@dataclass(frozen=True)
class CodexFinalizeLandingDecision:
    status: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CodexFinalizeLandingReport:
    commands: tuple[CodexFinalizeLandingCommandResult, ...]
    artifacts: tuple[CodexFinalizeLandingArtifactFinding, ...]


@dataclass(frozen=True)
class CodexFinalizeLandingResult:
    policy: CodexFinalizeLandingPolicy
    decision: CodexFinalizeLandingDecision
    report: CodexFinalizeLandingReport

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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

    environment_blocked = False
    environment_failed_stages: set[str] = set()
    authority_denied = False
    authority_denied_stages: set[str] = set()
    non_environment_stage_failure = False
    hosted_pending_stages: list[str] = []
    for result in command_results:
        if result.required and result.exit_code is None:
            if (
                request.defer_privileged_checks_to_hosted
                and result.stage in HOSTED_REQUIRED_STAGES
            ):
                hosted_pending_stages.append(result.stage)
                continue
            reasons.append(f"stage_failed:{result.stage}")
            non_environment_stage_failure = True
            continue
        if result.required and result.exit_code != 0:
            reasons.append(f"stage_failed:{result.stage}")
            authority_reason = _authority_denial_reason(result)
            environment_reason = _environment_precondition_reason(result)
            if authority_reason is not None:
                reasons.append(authority_reason)
                authority_denied = True
                authority_denied_stages.add(result.stage)
            elif environment_reason is not None:
                reasons.append(environment_reason)
                environment_blocked = True
                environment_failed_stages.add(result.stage)
            else:
                non_environment_stage_failure = True

    if request.defer_privileged_checks_to_hosted:
        reasons.extend(
            f"hosted_verification_pending:{stage}"
            for stage in HOSTED_REQUIRED_STAGES
            if stage in hosted_pending_stages
        )

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

    if request.defer_privileged_checks_to_hosted:
        missing_hosted_stages = sorted(set(HOSTED_REQUIRED_STAGES) - set(hosted_pending_stages))
        if missing_hosted_stages:
            reasons.append("hosted_privileged_stage_deferral_incomplete:" + ",".join(missing_hosted_stages))

    non_environment_reason = any(
        reason not in ({f"stage_failed:{stage}" for stage in environment_failed_stages}
                       | {f"stage_failed:{stage}" for stage in authority_denied_stages})
        and not reason.startswith("environment_precondition_unavailable:")
        and not reason.startswith("authority_denied:")
        for reason in reasons
    )

    if reasons:
        non_pending_reasons = [
            reason for reason in reasons
            if not reason.startswith("hosted_verification_pending:")
        ]
        if (
            request.defer_privileged_checks_to_hosted
            and hosted_pending_stages
            and not non_pending_reasons
        ):
            return CodexFinalizeLandingResult(
                pol,
                CodexFinalizeLandingDecision(
                    "ready_for_pr_submission",
                    tuple(f"hosted_verification_pending:{stage}" for stage in HOSTED_REQUIRED_STAGES),
                ),
                CodexFinalizeLandingReport(command_results, artifact_findings),
            )
        if "invalid_phase" in reasons:
            status = "manual_review_required"
        elif "unknown_dirty_tree" in reasons:
            status = "manual_review_required"
        elif authority_denied and not non_environment_stage_failure and not non_environment_reason:
            status = "authority_denied"
        elif environment_blocked and not non_environment_stage_failure and not non_environment_reason:
            status = "environment_blocked"
        else:
            status = "repair_required_task_caused"
        return CodexFinalizeLandingResult(pol, CodexFinalizeLandingDecision(status, tuple(reasons)), CodexFinalizeLandingReport(command_results, artifact_findings))

    if request.defer_privileged_checks_to_hosted:
        return CodexFinalizeLandingResult(
            pol,
            CodexFinalizeLandingDecision("repair_required_task_caused", ("hosted_privileged_verification_missing",)),
            CodexFinalizeLandingReport(command_results, artifact_findings),
        )
    ready_status = "ready_to_commit" if phase == "pre-commit" else "ready_for_pr_metadata"
    return CodexFinalizeLandingResult(pol, CodexFinalizeLandingDecision(ready_status, ()), CodexFinalizeLandingReport(command_results, artifact_findings))
