from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

REQUIRED_SECTIONS: tuple[str, ...] = (
    "### Motivation",
    "### Description",
    "### Testing",
    "### Full command matrix results",
    "### Matrix runner summary",
    "### Matrix runner output",
    "### Targeted mypy",
    "### Mypy baseline",
    "### Docs build",
    "### Prompt-boundary verification",
    "### Strict audit",
    "### Immutability verifier",
    "### Landing gate",
    "### Landing Supervisor",
    "### Finalizer status",
    "### PR metadata guard",
    "### Unresolved risks",
)

GUARD_REQUIRED_MARKERS: tuple[str, ...] = (
    "full command matrix results",
    "matrix runner --summary result",
    "matrix runner --output result/path",
    "targeted mypy result",
    "baseline result",
    "docs build result",
    "prompt-boundary result",
    "strict audit result",
    "immutability verifier result",
    "unresolved risks",
)

MATRIX_OUTPUT_PATH_PREFIX = "Matrix output path: "


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return parsed


def _load_optional_json_object(path_text: str) -> dict[str, Any] | None:
    if not path_text:
        return None
    path = Path(path_text)
    if not path.exists():
        return None
    return _load_json_object(path, label="landing supervisor JSON")


def _row_exit_code(matrix: Mapping[str, Any], labels: tuple[str, ...]) -> int | None:
    wanted = set(labels)
    rows = matrix.get("results", [])
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return None
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("label", "")) not in wanted:
            continue
        try:
            return int(row.get("exit_code", 1))
        except (TypeError, ValueError):
            return 1
    return None


def _exit_summary(matrix: Mapping[str, Any], labels: tuple[str, ...], *, default: str = "not recorded in matrix") -> str:
    exit_code = _row_exit_code(matrix, labels)
    if exit_code is None:
        return default
    return "passed (exit_code=0)" if exit_code == 0 else f"failed (exit_code={exit_code})"


def _matrix_command_lines(matrix: Mapping[str, Any]) -> list[str]:
    rows = matrix.get("results", [])
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return []
    lines: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        label = str(row.get("label", "unknown"))
        required = bool(row.get("required", True))
        try:
            exit_code = int(row.get("exit_code", 1))
        except (TypeError, ValueError):
            exit_code = 1
        command_value = row.get("command", [])
        if isinstance(command_value, Sequence) and not isinstance(command_value, (str, bytes)):
            command = " ".join(str(part) for part in command_value)
        else:
            command = str(command_value or "not recorded")
        lines.append(f"- {label}: exit_code={exit_code}; required={str(required).lower()}; command={command}")
    return lines


def _supervisor_summary(payload: Mapping[str, Any] | None, path_text: str) -> str:
    if payload is None:
        return f"Landing Supervisor result: pending or not yet written at {path_text}."
    decision = payload.get("decision")
    if isinstance(decision, Mapping):
        status = str(decision.get("status", "unknown"))
    else:
        status = str(payload.get("status", "unknown"))
    reasons_value = payload.get("report", {})
    reasons: object = []
    if isinstance(reasons_value, Mapping):
        reasons = reasons_value.get("reasons", [])
    return f"Landing Supervisor result: {status}; reasons={json.dumps(reasons, sort_keys=True)}."


def _text(value: str, fallback: str) -> str:
    stripped = value.strip()
    return stripped if stripped else fallback


def build_body(
    *,
    title: str,
    intended_commit_title: str,
    matrix_json_path: Path,
    landing_supervisor_json_path: str,
    targeted_mypy: str,
    baseline: str,
    docs_build: str,
    prompt_boundary: str,
    strict_audit: str,
    immutability_verifier: str,
    finalizer: str,
    pr_metadata_guard: str,
    unresolved_risks: str,
    landing_gate: str,
    motivation: str,
    description: str,
    testing: str,
) -> str:
    if not matrix_json_path.exists():
        raise ValueError(f"matrix-json-path does not exist: {matrix_json_path}")
    matrix = _load_json_object(matrix_json_path, label="matrix JSON")
    supervisor = _load_optional_json_object(landing_supervisor_json_path)

    status = str(matrix.get("status", "unknown"))
    required_failure_count = str(matrix.get("required_failure_count", "unknown"))
    command_count = str(matrix.get("command_count", len(_matrix_command_lines(matrix))))
    required_failures = matrix.get("required_failures", [])
    if not isinstance(required_failures, Sequence) or isinstance(required_failures, (str, bytes)):
        required_failures = []

    targeted_mypy_result = _text(targeted_mypy, _exit_summary(matrix, ("targeted_mypy",)))
    baseline_result = _text(baseline, _exit_summary(matrix, ("mypy_baseline",)))
    docs_build_result = _text(docs_build, _exit_summary(matrix, ("docs_build",)))
    prompt_boundary_result = _text(prompt_boundary, _exit_summary(matrix, ("prompt_boundaries", "prompt_boundary")))
    strict_audit_result = _text(strict_audit, _exit_summary(matrix, ("strict_audits", "strict_audit")))
    immutability_result = _text(immutability_verifier, _exit_summary(matrix, ("audit_immutability", "immutability_verifier")))
    unresolved = _text(unresolved_risks, "None known.")

    matrix_lines = _matrix_command_lines(matrix)
    matrix_lines_text = "\n".join(matrix_lines) if matrix_lines else "- Matrix contained no per-command rows."
    path_text = str(matrix_json_path)

    sections = [
        ("### Motivation", _text(motivation, "Harden Codex landing evidence so late PR metadata/finalizer failures retain canonical, repo-native recovery information instead of relying on hand-written evidence bodies.")),
        ("### Description", _text(description, f"Title: {title}\nIntended commit title: {intended_commit_title}\nGenerated from canonical matrix artifact and landing supervisor path.")),
        ("### Testing", _text(testing, "See full matrix, targeted checks, landing gate, supervisor, finalizer, and PR metadata guard sections below.")),
        (
            "### Full command matrix results",
            "\n".join(
                [
                    f"Full command matrix results: status={status}; required_failure_count={required_failure_count}; command_count={command_count}.",
                    f"Required failures: {json.dumps(list(required_failures), sort_keys=True)}.",
                    matrix_lines_text,
                ]
            ),
        ),
        ("### Matrix runner summary", f"Matrix runner --summary result: {status}; required_failure_count={required_failure_count}."),
        ("### Matrix runner output", f"Matrix runner --output result/path: {path_text}\n{MATRIX_OUTPUT_PATH_PREFIX}{path_text}"),
        ("### Targeted mypy", f"Targeted mypy result: {targeted_mypy_result}"),
        ("### Mypy baseline", f"Baseline result: {baseline_result}"),
        ("### Docs build", f"Docs build result: {docs_build_result}"),
        ("### Prompt-boundary verification", f"Prompt-boundary result: {prompt_boundary_result}"),
        ("### Strict audit", f"Strict audit result: {strict_audit_result}"),
        ("### Immutability verifier", f"Immutability verifier result: {immutability_result}"),
        ("### Landing gate", _text(landing_gate, "Landing gate result: pending until scripts/codex_pr_landing_gate.py verifies this generated body.")),
        ("### Landing Supervisor", _supervisor_summary(supervisor, landing_supervisor_json_path)),
        ("### Finalizer status", _text(finalizer, "Finalizer status: pending standard two-phase finalizer.")),
        ("### PR metadata guard", _text(pr_metadata_guard, "PR metadata guard: pending post-commit finalizer evidence.")),
        ("### Unresolved risks", f"Unresolved risks: {unresolved}"),
    ]
    body = "\n\n".join(f"{heading}\n{content.strip()}" for heading, content in sections).strip() + "\n"
    validate_body(body, matrix_json_path=matrix_json_path)
    return body


def validate_body(body: str, *, matrix_json_path: Path) -> None:
    normalized = " ".join(body.lower().replace("_", " ").split())
    if len(body.strip()) < 600:
        raise ValueError("generated body is evidence-light")
    missing_sections = [section for section in REQUIRED_SECTIONS if section not in body]
    if missing_sections:
        raise ValueError("generated body omitted required sections: " + ", ".join(missing_sections))
    if MATRIX_OUTPUT_PATH_PREFIX + str(matrix_json_path) not in body:
        raise ValueError("generated body omitted Matrix output path marker")
    if "### Unresolved risks" not in body or "unresolved risks:" not in normalized:
        raise ValueError("generated body omitted unresolved risks section")
    missing_markers = [marker for marker in GUARD_REQUIRED_MARKERS if marker not in normalized]
    if missing_markers:
        raise ValueError("generated body omitted PR metadata guard markers: " + ", ".join(missing_markers))
    placeholder_tokens = ("todo", "tbd", "placeholder-only")
    if any(token in normalized for token in placeholder_tokens):
        raise ValueError("generated body contains placeholder-only evidence")
    stale_tokens = ("stale evidence", "stale evidence matrix output", "stale matrix", "stale-evidence", "stale_evidence")
    ready_tokens = ("ready to commit", "ready for pr metadata", "ready_to_commit", "ready_for_pr_metadata", "pr metadata guard ready", "pr_metadata_guard_ready")
    for line in body.splitlines():
        normalized_line = " ".join(line.lower().replace("_", " ").split())
        if any(token in normalized_line for token in stale_tokens) and any(token in normalized_line for token in ready_tokens):
            raise ValueError("generated body contains contradictory stale-evidence and ready landing markers")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a deterministic Codex landing evidence PR body from canonical artifacts.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--intended-commit-title", required=True)
    parser.add_argument("--matrix-json-path", required=True)
    parser.add_argument("--landing-supervisor-json-path", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--targeted-mypy", default="")
    parser.add_argument("--baseline", default="")
    parser.add_argument("--docs-build", default="")
    parser.add_argument("--prompt-boundary", default="")
    parser.add_argument("--strict-audit", default="")
    parser.add_argument("--immutability-verifier", default="")
    parser.add_argument("--finalizer", default="")
    parser.add_argument("--pr-metadata-guard", default="")
    parser.add_argument("--unresolved-risks", default="None known.")
    parser.add_argument("--landing-gate", default="")
    parser.add_argument("--motivation", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--testing", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    matrix_json_path = Path(args.matrix_json_path)
    if not args.matrix_json_path.strip():
        print("matrix-json-path is required", file=sys.stderr)
        return 2
    try:
        body = build_body(
            title=args.title,
            intended_commit_title=args.intended_commit_title,
            matrix_json_path=matrix_json_path,
            landing_supervisor_json_path=args.landing_supervisor_json_path,
            targeted_mypy=args.targeted_mypy,
            baseline=args.baseline,
            docs_build=args.docs_build,
            prompt_boundary=args.prompt_boundary,
            strict_audit=args.strict_audit,
            immutability_verifier=args.immutability_verifier,
            finalizer=args.finalizer,
            pr_metadata_guard=args.pr_metadata_guard,
            unresolved_risks=args.unresolved_risks,
            landing_gate=args.landing_gate,
            motivation=args.motivation,
            description=args.description,
            testing=args.testing,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    Path(args.output).write_text(body, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
