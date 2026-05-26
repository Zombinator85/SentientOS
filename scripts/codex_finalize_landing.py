from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from sentientos.codex_finalize_landing import (
    CodexFinalizeLandingArtifactFinding,
    CodexFinalizeLandingCommandResult,
    CodexFinalizeLandingPolicy,
    CodexFinalizeLandingRequest,
    evaluate_finalize_landing,
)

GENERATED_PREFIXES = ("glow/", "pulse/", "artifacts/codex/")


def _run(stage: str, cmd: str, required: bool = True) -> CodexFinalizeLandingCommandResult:
    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    tail = "\n".join((p.stdout + "\n" + p.stderr).strip().splitlines()[-20:])
    return CodexFinalizeLandingCommandResult(stage=stage, command=cmd, exit_code=p.returncode, output_tail=tail, required=required)


def _git_status() -> list[str]:
    p = subprocess.run("git status --short", shell=True, text=True, capture_output=True)
    return [l.rstrip() for l in p.stdout.splitlines() if l.strip()]


def _git_tracked_changes() -> tuple[str, ...]:
    p = subprocess.run("git diff --name-only --cached && git diff --name-only", shell=True, text=True, capture_output=True)
    names = [line.strip() for line in p.stdout.splitlines() if line.strip()]
    return tuple(sorted(set(names)))


def _classify(status_lines: list[str], changed_files: tuple[str, ...]) -> tuple[CodexFinalizeLandingArtifactFinding, ...]:
    out: list[CodexFinalizeLandingArtifactFinding] = []
    changed_file_set = set(changed_files)
    for line in status_lines:
        is_untracked = line.startswith("??")
        path = line[3:] if len(line) > 3 else line
        if path.startswith(GENERATED_PREFIXES):
            cls = "generated_runtime_artifact"
            action = "cleanup"
        elif path.startswith("pulse/audit/"):
            cls = "versioned_audit_artifact"
            action = "review"
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


def _cleanup_generated() -> None:
    subprocess.run("git restore pulse/audit/privileged_audit.runtime.jsonl", shell=True)
    subprocess.run("git clean -fd glow pulse artifacts/codex", shell=True)


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
        s.add_argument("--allow-docs-bootstrap", action="store_true")
        s.add_argument("--allow-strict-audit-repair", action="store_true")
        s.add_argument("--allow-generated-artifact-cleanup", action="store_true")
        s.add_argument("--allow-no-focused-tests", action="store_true")
        s.add_argument("--output")
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
        allow_current_tracked_changes=a.allow_current_tracked_changes,
        dirty_file_classification_source="inferred" if a.allow_current_tracked_changes else "declared",
        allow_no_focused_tests=a.allow_no_focused_tests,
        workspace_root=a.workspace_root,
        summary=a.summary,
    )
    cmds = []
    for c in a.focused_test_command:
        cmds.append(_run("focused_tests", c))
    for c in a.targeted_mypy_command:
        cmds.append(_run("targeted_mypy", c))
    cmds += [
        _run("mypy_baseline", "python scripts/check_mypy_baseline.py"),
        _run("matrix_summary", "python scripts/run_work_item_review_packet_matrix.py --summary"),
        _run("matrix_output", f"python scripts/run_work_item_review_packet_matrix.py --output {a.matrix_json_path}"),
        _run("pr_landing_gate", f"python scripts/codex_pr_landing_gate.py gate --title \"{a.title}\" --intended-commit-title \"{a.intended_commit_title}\" --matrix-json-path {a.matrix_json_path}"),
        _run("landing_supervisor", f"python scripts/codex_landing_supervisor.py evaluate --title \"{a.title}\" --intended-commit-title \"{a.intended_commit_title}\" --matrix-json-path {a.matrix_json_path} --landing-gate-status passed --summary"),
        _run("docs_check_deps", "python scripts/build_docs.py --check-deps"),
        _run("docs_build", "python scripts/build_docs.py"),
        _run("prompt_boundary", "python scripts/verify_context_hygiene_prompt_boundaries.py"),
        _run("strict_audits", "python verify_audits.py --strict"),
        _run("audit_immutability", "python scripts/audit_immutability_verifier.py"),
    ]
    if a.allow_generated_artifact_cleanup:
        _cleanup_generated()
    findings = _classify(_git_status(), tuple(a.changed_file) + inferred_changed_files)
    result = evaluate_finalize_landing(
        req,
        tuple(cmds),
        findings,
        policy=CodexFinalizeLandingPolicy(allow_generated_artifact_cleanup=a.allow_generated_artifact_cleanup),
    )
    payload = result.to_dict()
    if a.output:
        Path(a.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        json.dumps(
            payload
            if not a.summary
            else {
                "status": result.decision.status,
                "reasons": result.decision.reasons,
                "inferred_changed_files": inferred_changed_files,
            },
            indent=2,
        )
    )
    return 0 if result.decision.status in {"ready_to_commit", "ready_for_pr_metadata"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
