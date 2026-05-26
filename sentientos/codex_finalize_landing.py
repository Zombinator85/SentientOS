from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


VALID_PHASES = {"pre-commit", "post-commit", "pr-metadata"}


@dataclass(frozen=True)
class CodexFinalizeLandingPolicy:
    require_focused_tests: bool = True
    require_targeted_mypy: bool = True
    require_mypy_baseline: bool = True
    require_matrix_summary: bool = True
    require_matrix_output: bool = True
    require_pr_landing_gate: bool = True
    require_landing_supervisor: bool = True
    require_docs_build: bool = True
    require_prompt_boundary: bool = True
    require_strict_audits: bool = True
    require_audit_immutability: bool = True
    require_clean_working_tree: bool = True
    allow_docs_bootstrap: bool = False
    allow_strict_audit_repair: bool = False
    allow_generated_artifact_cleanup: bool = False
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
    allow_no_focused_tests: bool = False
    workspace_root: str = "."
    summary: bool = False


@dataclass(frozen=True)
class CodexFinalizeLandingCommandResult:
    stage: str
    command: str
    exit_code: int
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

    for result in command_results:
        if result.required and result.exit_code != 0:
            reasons.append(f"stage_failed:{result.stage}")

    changed_file_set = set(request.changed_files)
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
        else:
            status = "repair_required_task_caused"
        return CodexFinalizeLandingResult(pol, CodexFinalizeLandingDecision(status, tuple(reasons)), CodexFinalizeLandingReport(command_results, artifact_findings))

    ready_status = "ready_to_commit" if phase == "pre-commit" else "ready_for_pr_metadata"
    return CodexFinalizeLandingResult(pol, CodexFinalizeLandingDecision(ready_status, ()), CodexFinalizeLandingReport(command_results, artifact_findings))
