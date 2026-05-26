from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


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
    focused_test_commands: tuple[str, ...] = ()
    targeted_mypy_commands: tuple[str, ...] = ()
    extra_required_commands: tuple[str, ...] = ()
    changed_files: tuple[str, ...] = ()
    allow_no_focused_tests: bool = False
    workspace_root: str = "."
    summary: bool = False


@dataclass(frozen=True)
class CodexFinalizeLandingCommandSpec:
    stage: str
    command: str
    required: bool = True


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


def evaluate_finalize_landing(
    request: CodexFinalizeLandingRequest,
    command_results: tuple[CodexFinalizeLandingCommandResult, ...],
    artifact_findings: tuple[CodexFinalizeLandingArtifactFinding, ...],
    policy: CodexFinalizeLandingPolicy | None = None,
) -> CodexFinalizeLandingResult:
    pol = policy or CodexFinalizeLandingPolicy()
    reasons: list[str] = []

    if request.title != request.intended_commit_title:
        reasons.append("title_mismatch")
    if pol.require_focused_tests and not request.focused_test_commands and not request.allow_no_focused_tests:
        reasons.append("focused_tests_missing")

    for result in command_results:
        if result.required and result.exit_code != 0:
            reasons.append(f"stage_failed:{result.stage}")

    unknown_dirty = any(a.classification == "unknown" for a in artifact_findings)
    if pol.require_clean_working_tree and unknown_dirty:
        reasons.append("unknown_dirty_tree")

    if reasons:
        decision = "manual_review_required" if "unknown_dirty_tree" in reasons else "repair_required_task_caused"
        return CodexFinalizeLandingResult(pol, CodexFinalizeLandingDecision(decision, tuple(reasons)), CodexFinalizeLandingReport(command_results, artifact_findings))

    return CodexFinalizeLandingResult(pol, CodexFinalizeLandingDecision("ready_for_pr_metadata", ()), CodexFinalizeLandingReport(command_results, artifact_findings))
