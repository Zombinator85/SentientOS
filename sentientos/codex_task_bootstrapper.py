from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sentientos.codex_task_scaffold import CodexTaskScaffoldRequest, build_codex_task_scaffold
from sentientos.codex_task_scaffold_path_planner import NONZERO, PlannerRequest, build_scaffold_request_payload, plan_codex_task_scaffold_paths
from sentientos.codex_task_scaffold_preset_verifier import verify_codex_task_scaffold_presets
from sentientos.codex_task_scaffold_verifier import verify_codex_task_scaffold_payload

READY = frozenset({"ready", "ready_with_warnings", "manual_review_required"})


@dataclass(frozen=True)
class CodexTaskBootstrapRequest:
    task_name: str
    task_goal: str
    preset_id: str = ""
    subsystem_kind: str = ""
    commit_scope: str = "developer"
    new_module: tuple[str, ...] = ()
    new_cli: tuple[str, ...] = ()
    test_path: tuple[str, ...] = ()
    doc_path: tuple[str, ...] = ()
    capability_id: str = ""
    proof_bundle_artifact_kind: str = ""
    commit_title: str = ""


@dataclass(frozen=True)
class CodexTaskBootstrapResult:
    status: str
    warning_codes: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    planner_result_summary: dict[str, Any]
    scaffold_result_summary: dict[str, Any]
    scaffold_verifier_result_summary: dict[str, Any]
    preset_verifier_result_summary: dict[str, Any]
    generated_prompt_text: str
    generated_scaffold_json: dict[str, Any]
    artifact_classification: str
    planned_paths: dict[str, str]
    explicit_non_authority_boundaries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _blocked_bootstrap_prompt(request: CodexTaskBootstrapRequest, blocker_codes: tuple[str, ...]) -> str:
    return (
        "BLOCKED_DO_NOT_IMPLEMENT\n"
        "This bootstrap output is diagnostic only and is not an implementation contract.\n"
        "Stop now: repair the blocker or ask the operator for a new task.\n"
        "Do not implement, do not commit, and do not make_pr from this blocked bootstrap artifact.\n"
        f"Diagnostic goal: {request.task_goal}\nDiagnostic task: {request.task_name}.\n"
        f"Blockers: {', '.join(blocker_codes) if blocker_codes else 'blocked'}."
    )


def _classified_scaffold_dict(payload: dict[str, Any], status: str) -> dict[str, Any]:
    classified = dict(payload)
    classified["artifact_classification"] = "diagnostic" if status == "blocked" else "implementation_contract"
    return classified


def bootstrap_codex_task(request: CodexTaskBootstrapRequest, *, include_preset_verifier: bool = True) -> CodexTaskBootstrapResult:
    planner_request = PlannerRequest(
        task_name=request.task_name,
        task_goal=request.task_goal,
        preset_id=request.preset_id,
        subsystem_kind=request.subsystem_kind,
        commit_scope=request.commit_scope,
        new_module=request.new_module,
        new_cli=request.new_cli,
        test_path=request.test_path,
        doc_path=request.doc_path,
        capability_id=request.capability_id,
        proof_bundle_artifact_kind=request.proof_bundle_artifact_kind,
        commit_title=request.commit_title,
    )
    planned = plan_codex_task_scaffold_paths(planner_request)
    scaffold_payload = build_scaffold_request_payload(planner_request, planned)
    scaffold_request = CodexTaskScaffoldRequest(
        task_name=request.task_name,
        task_goal=request.task_goal,
        subsystem_kind=request.subsystem_kind or request.preset_id,
        prompt_mode="whole_system",
        new_module_path=tuple(scaffold_payload["new_module_path"]),
        new_cli_path=tuple(scaffold_payload["new_cli_path"]),
        expected_test_paths=tuple(scaffold_payload["expected_test_paths"]),
        expected_doc_paths=tuple(scaffold_payload["expected_doc_paths"]),
        capability_id=str(scaffold_payload["capability_id"]),
        proof_bundle_artifact_kind=str(scaffold_payload["proof_bundle_artifact_kind"]),
        commit_title=str(scaffold_payload["commit_title"]),
    )
    scaffold = build_codex_task_scaffold(scaffold_request)
    verifier = verify_codex_task_scaffold_payload(scaffold.to_dict())
    preset_verifier_summary: dict[str, Any] = {}
    if include_preset_verifier and scaffold_request.subsystem_kind:
        preset_result = verify_codex_task_scaffold_presets(scaffold_request.subsystem_kind)
        preset_verifier_summary = preset_result.to_dict()

    warning_codes = tuple(sorted(set(planned.warning_codes + scaffold.scaffold.warning_codes)))
    blocker_codes = list(planned.blocker_codes + scaffold.scaffold.blocker_codes)
    if verifier.status != "codex_task_scaffold_verifier_ready":
        warning_codes = tuple(sorted(set(warning_codes + ("scaffold_verifier_incomplete",))))
    if preset_verifier_summary and preset_verifier_summary.get("status") != "codex_task_scaffold_preset_verifier_ready":
        warning_codes = tuple(sorted(set(warning_codes + ("preset_verifier_incomplete",))))
    status = "ready" if not blocker_codes and planned.status not in NONZERO else "blocked"
    if status == "ready" and warning_codes:
        status = "ready_with_warnings"

    return CodexTaskBootstrapResult(
        status=status,
        warning_codes=warning_codes,
        blocker_codes=tuple(sorted(set(blocker_codes))),
        planner_result_summary={"status": planned.status, "task_slug": planned.task_slug},
        scaffold_result_summary={"status": scaffold.status, "scaffold_id": scaffold.scaffold.scaffold_id},
        scaffold_verifier_result_summary=verifier.to_dict(),
        preset_verifier_result_summary=preset_verifier_summary,
        generated_prompt_text=_blocked_bootstrap_prompt(request, tuple(sorted(set(blocker_codes)))) if status == "blocked" else scaffold.scaffold.generated_prompt,
        generated_scaffold_json=_classified_scaffold_dict(scaffold.to_dict(), status),
        artifact_classification="diagnostic" if status == "blocked" else "implementation_contract",
        planned_paths={
            "module_path": planned.module_path,
            "cli_path": planned.cli_path,
            "api_test_path": planned.api_test_path,
            "cli_test_path": planned.cli_test_path,
            "dev_doc_path": planned.dev_doc_path,
            "proof_bundle_filename": planned.proof_bundle_filename,
        },
        explicit_non_authority_boundaries=(
            "metadata-only bootstrap flow",
            "no codex invocation",
            "no provider/network/github/shell/subprocess/action-wing invocation",
            "no repo mutation except explicit output artifacts",
        ),
    )


def write_bootstrap_artifacts(result: CodexTaskBootstrapResult, *, summary_output: Path | None = None, plan_output: Path | None = None, scaffold_output: Path | None = None, prompt_output: Path | None = None, verifier_output: Path | None = None) -> None:
    def _dump(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if summary_output:
        _dump(summary_output, result.to_dict())
    if plan_output:
        _dump(plan_output, result.planner_result_summary | result.planned_paths)
    if scaffold_output:
        _dump(scaffold_output, result.generated_scaffold_json)
    if prompt_output:
        prompt_output.parent.mkdir(parents=True, exist_ok=True)
        prompt_output.write_text(result.generated_prompt_text + "\n", encoding="utf-8")
    if verifier_output:
        _dump(verifier_output, {
            "scaffold": result.scaffold_verifier_result_summary,
            "preset": result.preset_verifier_result_summary,
        })
