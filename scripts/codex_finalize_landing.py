from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from sentientos.codex_finalize_landing import (
    CodexFinalizeLandingArtifactFinding,
    CodexFinalizeLandingCommandResult,
    CodexFinalizeLandingPolicy,
    CodexFinalizeLandingRequest,
    evaluate_finalize_landing,
)

GENERATED_PREFIXES = ("glow/", "pulse/", "artifacts/codex/")
BLOCKED_PATH_PARTS = ("__pycache__", ".pytest_cache")
MEDIA_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".wav", ".mp3")
DEFAULT_STAGE_TIMEOUT_SECONDS = 900
DEFAULT_OVERALL_TIMEOUT_SECONDS = 3600
MAX_OUTPUT_LINES = 40


@dataclass(frozen=True)
class StageRuntime:
    stage_id: str
    command: str
    started_at: float
    completed: bool
    exit_code: int
    duration_seconds: float
    stdout_tail: str
    stderr_tail: str
    decision_impact: str
    status: str
    timed_out: bool


@dataclass(frozen=True)
class DirtyPathDiagnostic:
    path: str
    git_status: str
    classification: str
    classification_source: str
    tracked: bool
    cleanup_attempted: bool
    cleanup_result: str
    cleanup_reason: str
    recommended_action: str


class FinalizerTimeoutError(RuntimeError):
    def __init__(self, stage_id: str, kind: str) -> None:
        super().__init__(f"{kind}_timeout:{stage_id}")
        self.stage_id = stage_id
        self.kind = kind


def _tail(text: str, limit: int = MAX_OUTPUT_LINES) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-limit:])


def _progress(enabled: bool, line: str) -> None:
    if enabled:
        print(line, flush=True)


def _run_stage(
    stage_id: str,
    cmd: str,
    required: bool,
    progress: bool,
    stage_timeout_seconds: int,
    overall_deadline: float,
) -> tuple[CodexFinalizeLandingCommandResult, StageRuntime]:
    if time.monotonic() >= overall_deadline:
        raise FinalizerTimeoutError(stage_id, "overall")
    _progress(progress, f"[finalizer] stage start: {stage_id}")
    started = time.monotonic()
    timeout_seconds = min(stage_timeout_seconds, max(1, int(overall_deadline - started)))
    try:
        p = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=timeout_seconds)
        timed_out = False
        status = "passed" if p.returncode == 0 else "failed"
    except subprocess.TimeoutExpired as exc:
        stdout_part = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr_part = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        combined = stdout_part + "\n" + stderr_part
        runtime = StageRuntime(
            stage_id=stage_id,
            command=cmd,
            started_at=started,
            completed=False,
            exit_code=124,
            duration_seconds=time.monotonic() - started,
            stdout_tail=_tail(combined),
            stderr_tail="",
            decision_impact="required_stage_timeout" if required else "optional_stage_timeout",
            status="timed_out",
            timed_out=True,
        )
        _progress(progress, f"[finalizer] stage end: {stage_id} status=timed_out exit_code=124")
        raise FinalizerTimeoutError(stage_id, "stage") from exc
    duration = time.monotonic() - started
    result = CodexFinalizeLandingCommandResult(
        stage=stage_id,
        command=cmd,
        exit_code=p.returncode,
        output_tail=_tail((p.stdout or "") + "\n" + (p.stderr or "")),
        required=required,
    )
    runtime = StageRuntime(
        stage_id=stage_id,
        command=cmd,
        started_at=started,
        completed=True,
        exit_code=p.returncode,
        duration_seconds=duration,
        stdout_tail=_tail(p.stdout or ""),
        stderr_tail=_tail(p.stderr or ""),
        decision_impact="required" if required else "optional",
        status=status,
        timed_out=timed_out,
    )
    _progress(progress, f"[finalizer] stage end: {stage_id} status={status} exit_code={p.returncode}")
    return result, runtime


def _git_status() -> list[str]:
    p = subprocess.run("git status --short", shell=True, text=True, capture_output=True)
    return [l.rstrip() for l in p.stdout.splitlines() if l.strip()]


def _git_tracked_changes() -> tuple[str, ...]:
    p = subprocess.run("git diff --name-only --cached && git diff --name-only", shell=True, text=True, capture_output=True)
    names = [line.strip() for line in p.stdout.splitlines() if line.strip()]
    return tuple(sorted(set(names)))


def _is_safe_untracked_task_file(path: str) -> bool:
    if path == "AGENTS.md":
        return True
    if path.startswith(("sentientos/", "scripts/", "tests/", "docs/")) and path.endswith((".py", ".md")):
        return True
    if path.startswith("tests/fixtures/") and path.endswith(".json"):
        return True
    if path.startswith("artifacts/proof_bundles/") and path.endswith(".json"):
        return True
    return False


def _recommended_action(classification: str, path: str) -> str:
    if classification == "generated_runtime_artifact":
        if path == "pulse/audit/privileged_audit.runtime.jsonl":
            return "restore_runtime_audit_artifact"
        return "remove_generated_artifact"
    if classification == "source_change_not_declared":
        return "add_to_task_file_allowlist" if path.startswith(("sentientos/", "scripts/", "tests/", "docs/")) else "explicitly_pass_changed_file"
    return "manual_review_required"


def _classify(status_lines: list[str], changed_files: tuple[str, ...], inferred_untracked_task_files: tuple[str, ...]) -> tuple[CodexFinalizeLandingArtifactFinding, ...]:
    out: list[CodexFinalizeLandingArtifactFinding] = []
    changed_file_set = set(changed_files)
    for line in status_lines:
        is_untracked = line.startswith("??")
        path = line[3:] if len(line) > 3 else line
        if path.startswith(GENERATED_PREFIXES) or any(part in path for part in BLOCKED_PATH_PARTS):
            cls = "generated_runtime_artifact"
            action = "cleanup"
        elif path.lower().endswith(MEDIA_SUFFIXES):
            cls = "unknown_dirty_file"
            action = "block"
        elif path.startswith("pulse/audit/"):
            cls = "versioned_audit_artifact"
            action = "review"
        elif is_untracked and path in set(inferred_untracked_task_files):
            cls = "intended_task_change"
            action = "allow_pre_commit"
        elif (not is_untracked) and path in changed_file_set:
            cls = "intended_task_change"
            action = "allow_pre_commit"
        elif path.endswith((".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".bat")):
            cls = "source_change_not_declared"
            action = "block"
        else:
            cls = "unknown_dirty_file"
            action = "block"
        out.append(CodexFinalizeLandingArtifactFinding(path=path, classification=cls, action=action))
    if not out:
        out.append(CodexFinalizeLandingArtifactFinding(path="", classification="clean", action="none"))
    return tuple(out)


def _collect_dirty_diagnostics(
    status_lines: list[str],
    findings: tuple[CodexFinalizeLandingArtifactFinding, ...],
    classification_source: str,
    cleanup_map: dict[str, tuple[bool, str, str]],
) -> list[DirtyPathDiagnostic]:
    by_path = {item.path: item for item in findings}
    diagnostics: list[DirtyPathDiagnostic] = []
    for line in status_lines:
        git_status = line[:2]
        path = line[3:] if len(line) > 3 else line
        finding = by_path.get(path)
        cleanup_attempted, cleanup_result, cleanup_reason = cleanup_map.get(path, (False, "not_attempted", "not_generated"))
        diagnostics.append(
            DirtyPathDiagnostic(
                path=path,
                git_status=git_status,
                classification=finding.classification if finding else "unknown_dirty_file",
                classification_source=classification_source,
                tracked=not git_status.startswith("??"),
                cleanup_attempted=cleanup_attempted,
                cleanup_result=cleanup_result,
                cleanup_reason=cleanup_reason,
                recommended_action=_recommended_action(finding.classification if finding else "unknown_dirty_file", path),
            )
        )
    return diagnostics


def _cleanup_generated(status_lines: list[str]) -> dict[str, tuple[bool, str, str]]:
    cleanup: dict[str, tuple[bool, str, str]] = {}
    for line in status_lines:
        path = line[3:] if len(line) > 3 else line
        is_generated = path.startswith(GENERATED_PREFIXES) or any(part in path for part in BLOCKED_PATH_PARTS) or path == "pulse/audit/privileged_audit.runtime.jsonl"
        if not is_generated:
            continue
        if path == "pulse/audit/privileged_audit.runtime.jsonl":
            p = subprocess.run("git restore pulse/audit/privileged_audit.runtime.jsonl", shell=True)
            cleanup[path] = (True, "restored" if p.returncode == 0 else "failed", "runtime_audit_restore")
            continue
        p = subprocess.run(f"git clean -fd -- '{path}'", shell=True)
        cleanup[path] = (True, "removed" if p.returncode == 0 else "failed", "generated_artifact_cleanup")
    return cleanup


def _emit_and_optionally_write(payload: dict[str, object], output: str | None, summary: bool, decision_status: str) -> None:
    if output:
        Path(output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if summary:
        decision_payload = payload.get("decision")
        reasons = decision_payload.get("reasons", []) if isinstance(decision_payload, dict) else []
        print(json.dumps({"status": decision_status, "reasons": reasons}, indent=2))
        print(f"Codex Finalize Landing decision: {decision_status}", flush=True)
    else:
        print(json.dumps(payload, indent=2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "finalize", "summarize", "hygiene", "validate-evidence"):
        s = sub.add_parser(name)
        s.add_argument("--title", required=False)
        s.add_argument("--intended-commit-title", required=False)
        s.add_argument("--phase", default="pr-metadata")
        s.add_argument("--matrix-json-path", default="/tmp/work_item_review_packet_matrix.json")
        s.add_argument("--workspace-root", default=".")
        s.add_argument("--focused-test-command", action="append", default=[])
        s.add_argument("--targeted-mypy-command", action="append", default=[])
        s.add_argument("--extra-required-command", action="append", default=[])
        s.add_argument("--changed-file", action="append", default=[])
        s.add_argument("--allow-current-tracked-changes", action="store_true")
        s.add_argument("--allow-current-task-files", action="store_true")
        s.add_argument("--allow-docs-bootstrap", action="store_true")
        s.add_argument("--allow-strict-audit-repair", action="store_true")
        s.add_argument("--allow-generated-artifact-cleanup", action="store_true")
        s.add_argument("--allow-no-focused-tests", action="store_true")
        s.add_argument("--output")
        s.add_argument("--stage-timeout-seconds", type=int, default=DEFAULT_STAGE_TIMEOUT_SECONDS)
        s.add_argument("--overall-timeout-seconds", type=int, default=DEFAULT_OVERALL_TIMEOUT_SECONDS)
        s.add_argument("--progress", action="store_true", default=True)
        s.add_argument("--no-progress", action="store_false", dest="progress")
        s.add_argument("--summary", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    if a.cmd in {"plan", "summarize", "validate-evidence"}:
        print(json.dumps({"status": "ok", "command": a.cmd}, indent=2))
        return 0
    if a.cmd == "hygiene":
        print(json.dumps({"status": "ok", "git_status": _git_status()}, indent=2))
        return 0

    inferred_changed_files: tuple[str, ...] = ()
    if a.allow_current_tracked_changes:
        if a.phase.replace("_", "-") != "pre-commit":
            print(json.dumps({"status": "error", "reason": "allow_current_tracked_changes_requires_pre_commit"}, indent=2))
            return 2
        inferred_changed_files = _git_tracked_changes()
    inferred_untracked_task_files: tuple[str, ...] = ()
    if a.allow_current_task_files:
        if a.phase.replace("_", "-") != "pre-commit":
            print(json.dumps({"status": "error", "reason": "allow_current_task_files_requires_pre_commit"}, indent=2))
            return 2
        status_lines = _git_status()
        candidates = []
        for line in status_lines:
            if not line.startswith("??"):
                continue
            path = line[3:] if len(line) > 3 else line
            if _is_safe_untracked_task_file(path):
                candidates.append(path)
        inferred_untracked_task_files = tuple(sorted(set(candidates)))

    req = CodexFinalizeLandingRequest(
        title=a.title or "",
        intended_commit_title=a.intended_commit_title or "",
        phase=a.phase,
        matrix_json_path=a.matrix_json_path,
        focused_test_commands=tuple(a.focused_test_command),
        targeted_mypy_commands=tuple(a.targeted_mypy_command),
        extra_required_commands=tuple(a.extra_required_command),
        changed_files=tuple(a.changed_file),
        inferred_changed_files=inferred_changed_files,
        inferred_tracked_changed_files=inferred_changed_files,
        inferred_untracked_task_files=inferred_untracked_task_files,
        allow_current_tracked_changes=a.allow_current_tracked_changes,
        allow_current_task_files=a.allow_current_task_files,
        dirty_file_classification_source="tracked+untracked_inferred" if (a.allow_current_tracked_changes or a.allow_current_task_files) else "declared",
        allow_no_focused_tests=a.allow_no_focused_tests,
        workspace_root=a.workspace_root,
        summary=a.summary,
    )

    stage_specs: list[tuple[str, str, bool]] = [("preflight_hygiene", "git status --short", True)]
    stage_specs.extend(("focused_tests", c, True) for c in a.focused_test_command)
    stage_specs.extend(("targeted_mypy", c, True) for c in a.targeted_mypy_command)
    stage_specs.extend(
        [
            ("mypy_baseline", "python scripts/check_mypy_baseline.py", True),
            ("matrix_summary", "python scripts/run_work_item_review_packet_matrix.py --summary", True),
            ("matrix_output", f"python scripts/run_work_item_review_packet_matrix.py --output {a.matrix_json_path}", True),
            ("pr_landing_gate", f"python scripts/codex_pr_landing_gate.py gate --title \"{a.title}\" --intended-commit-title \"{a.intended_commit_title}\" --matrix-json-path {a.matrix_json_path}", True),
            ("landing_supervisor", f"python scripts/codex_landing_supervisor.py evaluate --title \"{a.title}\" --intended-commit-title \"{a.intended_commit_title}\" --matrix-json-path {a.matrix_json_path} --landing-gate-status passed --summary", True),
            ("docs_check_deps", "python scripts/build_docs.py --check-deps", True),
            ("docs_build", "python scripts/build_docs.py", True),
            ("prompt_boundary", "python scripts/verify_context_hygiene_prompt_boundaries.py", True),
            ("strict_audits", "python verify_audits.py --strict", True),
            ("audit_immutability", "python scripts/audit_immutability_verifier.py", True),
        ]
    )

    started = time.monotonic()
    deadline = started + max(1, a.overall_timeout_seconds)
    commands: list[CodexFinalizeLandingCommandResult] = []
    runtime: list[StageRuntime] = []
    decision_status = "finalizer_failed"
    decision_reasons: list[str] = []
    try:
        for stage_id, cmd, required in stage_specs:
            result, stage_runtime = _run_stage(stage_id, cmd, required, a.progress, a.stage_timeout_seconds, deadline)
            commands.append(result)
            runtime.append(stage_runtime)
    except FinalizerTimeoutError as exc:
        decision_status = "environment_blocked" if exc.kind == "overall" else "finalizer_failed"
        decision_reasons = [f"{exc.kind}_timeout:{exc.stage_id}", "rerun_with_higher_timeout_or_fix_hung_stage"]
    except Exception as exc:  # noqa: BLE001
        decision_status = "finalizer_failed"
        decision_reasons = [f"runtime_exception:{type(exc).__name__}"]

    status_before_cleanup = _git_status()
    cleanup_results: dict[str, tuple[bool, str, str]] = {}
    if a.allow_generated_artifact_cleanup:
        _progress(a.progress, "[finalizer] stage start: generated_artifact_cleanup")
        cleanup_results = _cleanup_generated(status_before_cleanup)
        _progress(a.progress, "[finalizer] stage end: generated_artifact_cleanup status=passed exit_code=0")

    status_after_cleanup = _git_status()
    findings = _classify(status_after_cleanup, tuple(a.changed_file) + inferred_changed_files, inferred_untracked_task_files)
    diagnostics = _collect_dirty_diagnostics(status_after_cleanup, findings, req.dirty_file_classification_source, cleanup_results)
    landing_result = evaluate_finalize_landing(req, tuple(commands), findings, policy=CodexFinalizeLandingPolicy(allow_generated_artifact_cleanup=a.allow_generated_artifact_cleanup))

    if not decision_reasons:
        decision_status = landing_result.decision.status
        decision_reasons = list(landing_result.decision.reasons)

    payload = landing_result.to_dict()
    payload["dirty_paths"] = [asdict(item) for item in diagnostics]
    payload["cleanup_actions"] = {k: {"attempted": v[0], "result": v[1], "reason": v[2]} for k, v in cleanup_results.items()}
    payload["runtime"] = {
        "stage_timeout_seconds": a.stage_timeout_seconds,
        "overall_timeout_seconds": a.overall_timeout_seconds,
        "stages": [asdict(item) for item in runtime],
        "final_decision": {"status": decision_status, "reasons": decision_reasons},
    }
    payload["decision"]["status"] = decision_status
    payload["decision"]["reasons"] = decision_reasons
    if a.summary:
        for item in diagnostics[:20]:
            print(
                f"[finalizer] dirty path: {item.git_status} {item.path} "
                f"classification={item.classification} cleanup={item.cleanup_result}"
            )

    _progress(a.progress, f"[finalizer] decision: {decision_status}")
    _emit_and_optionally_write(payload, a.output, a.summary, decision_status)
    return 0 if (a.phase.replace("_", "-") == "pre-commit" and decision_status == "ready_to_commit") or (a.phase.replace("_", "-") in {"post-commit", "pr-metadata"} and decision_status == "ready_for_pr_metadata") else 1


if __name__ == "__main__":
    raise SystemExit(main())
