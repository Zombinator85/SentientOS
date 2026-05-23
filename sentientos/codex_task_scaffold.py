from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

STATUSES = frozenset({
    "codex_task_scaffold_ready",
    "codex_task_scaffold_ready_with_warnings",
    "codex_task_scaffold_manual_review_required",
    "codex_task_scaffold_insufficient_metadata",
    "codex_task_scaffold_blocked",
    "codex_task_scaffold_failed",
})
PROMPT_MODES = frozenset({"whole_system", "narrow_repair"})
DEFAULT_VALIDATION_COMMANDS = (
    "python -m scripts.run_tests -q tests/test_codex_task_scaffold.py tests/test_build_codex_task_scaffold_script.py",
    "python -m mypy sentientos/codex_task_scaffold.py scripts/build_codex_task_scaffold.py",
)

@dataclass(frozen=True)
class CodexTaskScaffoldPolicy:
    default_prompt_mode: str = "whole_system"
    require_full_matrix_default: bool = True
    require_capability_registry_default: bool = True
    require_proof_bundle_default: bool = True
    require_docs_default: bool = True
    require_matrix_runner_default: bool = True
    require_safety_tests_default: bool = True


@dataclass(frozen=True)
class CodexTaskScaffoldRequest:
    task_name: str = ""
    task_goal: str = ""
    subsystem_kind: str = ""
    prompt_mode: str = "whole_system"
    current_chain_context: tuple[str, ...] = ()
    deliverables: tuple[str, ...] = ()
    new_module_path: tuple[str, ...] = ()
    new_cli_path: tuple[str, ...] = ()
    expected_test_paths: tuple[str, ...] = ()
    expected_doc_paths: tuple[str, ...] = ()
    capability_id: str = ""
    proof_bundle_artifact_kind: str = ""
    allowed_behaviors: tuple[str, ...] = ()
    forbidden_behaviors: tuple[str, ...] = ()
    validation_commands: tuple[str, ...] = ()
    commit_title: str = ""
    require_full_matrix: bool = True
    require_capability_registry: bool = True
    require_proof_bundle: bool = True
    require_docs: bool = True
    require_matrix_runner: bool = True
    require_safety_tests: bool = True


@dataclass(frozen=True)
class CodexTaskScaffoldSection:
    title: str
    body: str


@dataclass(frozen=True)
class CodexTaskScaffold:
    scaffold_id: str
    scaffold_digest: str
    task_name: str
    task_goal: str
    subsystem_kind: str
    prompt_mode: str
    generated_prompt: str
    validation_commands: tuple[str, ...]
    expected_files: tuple[str, ...]
    expected_tests: tuple[str, ...]
    expected_docs: tuple[str, ...]
    required_integrations: tuple[str, ...]
    forbidden_surfaces: tuple[str, ...]
    final_report_contract: tuple[str, ...]
    commit_pr_title: str
    doctrine_references: tuple[str, ...]
    artifact_references: tuple[str, ...]
    warning_codes: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    explicit_non_authority_boundaries: tuple[str, ...]


@dataclass(frozen=True)
class CodexTaskScaffoldResult:
    status: str
    scaffold: CodexTaskScaffold

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _norm(items: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({item.strip() for item in items if item and item.strip()}))


TITLE_RE = re.compile(r"^\[codex:[a-z0-9-]+\]\s+.+$")


def build_codex_task_scaffold(request: CodexTaskScaffoldRequest, policy: CodexTaskScaffoldPolicy | None = None) -> CodexTaskScaffoldResult:
    _ = policy or CodexTaskScaffoldPolicy()
    warnings: list[str] = []
    blockers: list[str] = []
    if not request.task_name.strip() or not request.task_goal.strip() or not request.subsystem_kind.strip():
        blockers.append("insufficient_required_metadata")
    if request.prompt_mode not in PROMPT_MODES:
        blockers.append("invalid_prompt_mode")
    if request.commit_title and not TITLE_RE.match(request.commit_title):
        warnings.append("nonconforming_commit_title")
    all_text = "\n".join(request.allowed_behaviors + request.forbidden_behaviors + request.deliverables + request.current_chain_context)
    banned = ("invoke codex", "openai", "provider", "github api", "create branch", "create pr", "subprocess", "shell execution", "workspace execution", "lifecycle orchestration")
    if any(term in all_text.lower() for term in banned):
        blockers.append("forbidden_authority_surface_requested")
    if request.prompt_mode == "whole_system" and not (request.new_module_path or request.new_cli_path or request.expected_test_paths or request.expected_doc_paths):
        warnings.append("whole_system_paths_missing")

    validation_commands = _norm(request.validation_commands or DEFAULT_VALIDATION_COMMANDS)
    expected_files = _norm(request.new_module_path + request.new_cli_path)
    expected_tests = _norm(request.expected_test_paths)
    expected_docs = _norm(request.expected_doc_paths)
    forbidden = _norm(request.forbidden_behaviors or (
        "Do not invoke Codex.", "Do not call OpenAI/provider APIs.", "Do not call GitHub APIs.", "Do not invoke shell/subprocess from library code.",
    ))
    required_integrations = _norm(
        tuple(x for x, enabled in (
            ("capability_registry", request.require_capability_registry),
            ("reviewer_proof_bundle", request.require_proof_bundle),
            ("docs", request.require_docs),
            ("matrix_runner", request.require_matrix_runner),
            ("safety_tests", request.require_safety_tests),
        ) if enabled)
    )
    if request.prompt_mode == "whole_system":
        prompt = (
            "Use AGENTS.md Whole-System Codex Operating Doctrine, whole-system task template, and validation/landing contract.\n"
            "Critical landing rule: run the full relevant validation matrix after the final task-caused code/doc/test change and before final reporting or PR metadata.\n"
            "Do not return 'feature exists but full matrix not run.' Do not offer to run matrix later.\n"
            "Do not create PR metadata before green final validation.\n"
            f"Goal: {request.task_goal}\nSubsystem: {request.task_name} ({request.subsystem_kind})."
        )
    else:
        prompt = (
            "Use AGENTS.md narrow repair doctrine and keep scope explicitly narrow.\n"
            "No whole-system expansion unless task-caused fallout requires it.\n"
            "Run minimal relevant validation and regression checks.\n"
            "If no changes are required, do not fabricate commit/PR metadata.\n"
            f"Goal: {request.task_goal}\nRepair target: {request.task_name} ({request.subsystem_kind})."
        )
    payload = {
        "task_name": request.task_name,
        "task_goal": request.task_goal,
        "subsystem_kind": request.subsystem_kind,
        "prompt_mode": request.prompt_mode,
        "prompt": prompt,
        "validation_commands": validation_commands,
        "expected_files": expected_files,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    scaffold = CodexTaskScaffold(
        scaffold_id=f"codex-task-scaffold-{digest[:12]}",
        scaffold_digest=digest,
        task_name=request.task_name,
        task_goal=request.task_goal,
        subsystem_kind=request.subsystem_kind,
        prompt_mode=request.prompt_mode,
        generated_prompt=prompt,
        validation_commands=validation_commands,
        expected_files=expected_files,
        expected_tests=expected_tests,
        expected_docs=expected_docs,
        required_integrations=required_integrations,
        forbidden_surfaces=forbidden,
        final_report_contract=("exact files changed", "full command matrix results", "unresolved risks"),
        commit_pr_title=request.commit_title,
        doctrine_references=("AGENTS.md", "docs/development/codex_whole_system_task_template.md", "docs/development/codex_validation_and_landing_contract.md"),
        artifact_references=("json_scaffold", "prompt_text"),
        warning_codes=tuple(sorted(warnings)),
        blocker_codes=tuple(sorted(blockers)),
        explicit_non_authority_boundaries=("developer workflow scaffolding only", "no runtime authority expansion"),
    )
    status = "codex_task_scaffold_ready"
    if blockers:
        status = "codex_task_scaffold_insufficient_metadata" if "insufficient_required_metadata" in blockers else "codex_task_scaffold_blocked"
    elif warnings:
        status = "codex_task_scaffold_ready_with_warnings"
    return CodexTaskScaffoldResult(status=status, scaffold=scaffold)


def write_scaffold_artifact(result: CodexTaskScaffoldResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_prompt_artifact(result: CodexTaskScaffoldResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.scaffold.generated_prompt + "\n", encoding="utf-8")
