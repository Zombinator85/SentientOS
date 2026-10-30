from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence
from sentientos.codex_landing_evidence_binding import file_sha256, create_body_binding, verify_body_binding
from sentientos.codex_pr_metadata_contract import verify_pr_metadata
from sentientos.landing_validation_plan import SOLO_MATRIX_STATUS, verify_validation_plan, verify_validation_plan_transition

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


def _stage_summary(
    matrix: Mapping[str, Any],
    finalizers: Sequence[Mapping[str, Any]],
    labels: tuple[str, ...],
) -> str:
    matrix_code = _row_exit_code(matrix, labels)
    if matrix_code is not None:
        return "passed (exit_code=0)" if matrix_code == 0 else f"failed (exit_code={matrix_code})"
    wanted = set(labels)
    for payload in finalizers:
        report = payload.get("report")
        commands = report.get("commands") if isinstance(report, Mapping) else None
        if not isinstance(commands, Sequence) or isinstance(commands, (str, bytes)):
            continue
        matches = [row for row in commands if isinstance(row, Mapping) and str(row.get("stage", "")) in wanted]
        if matches:
            row = matches[-1]
            try:
                exit_code = int(row.get("exit_code", 1))
            except (TypeError, ValueError):
                exit_code = 1
            result = "passed" if exit_code == 0 else "failed"
            return f"{result} by finalizer (exit_code={exit_code})"
    return "not recorded in matrix or finalizer"


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


def _supervisor_summary(
    payload: Mapping[str, Any] | None,
    path_text: str,
    *,
    validation_profile: str,
) -> str:
    if payload is None:
        if validation_profile == "solo":
            return "Landing Supervisor result: not required by the sealed solo validation profile."
        location = path_text or "no artifact path supplied"
        return f"Landing Supervisor result: pending or not yet written at {location}."
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


def _artifact_status(payload: Mapping[str, Any], *, label: str) -> str:
    decision = payload.get("decision")
    if isinstance(decision, Mapping):
        status = decision.get("status")
        if isinstance(status, str) and status:
            return status
    elif isinstance(decision, str) and decision:
        return decision
    status = payload.get("status")
    if isinstance(status, str) and status:
        return status
    plan = payload.get("landing_validation_plan")
    if isinstance(plan, Mapping):
        status = plan.get("overall_status")
        if isinstance(status, str) and status:
            return status
    raise ValueError(f"{label} artifact has no authoritative status")


def _status_summary_override(value: str, statuses: Sequence[str], *, label: str) -> None:
    """Do not let free-form body text contradict a supplied decision artifact."""
    normalized = " ".join(value.lower().replace("_", " ").split())
    if any(token in normalized for token in ("stale evidence", "stale matrix", "stale-evidence")):
        raise ValueError(f"{label} text contains stale-evidence markers")
    for status in statuses:
        if not status:
            continue
        normalized_status = " ".join(status.lower().replace("_", " ").split())
        negative_claim = re.search(
            rf"\b(?:not|failed|blocked|denied|without)\s+(?:status\s+)?{re.escape(normalized_status)}\b",
            normalized,
        )
        if negative_claim is not None:
            raise ValueError(f"{label} text negates artifact status {status}")
        if normalized_status not in normalized:
            raise ValueError(f"{label} text does not report artifact status {status}")


def _finalizer_summary(
    supplied: str,
    pre_payload: Mapping[str, Any],
    post_payload: Mapping[str, Any],
) -> str:
    statuses: list[str] = []
    if pre_payload:
        statuses.append(_artifact_status(pre_payload, label="pre-commit finalizer"))
    if post_payload:
        statuses.append(_artifact_status(post_payload, label="PR-metadata finalizer"))
    if not statuses:
        return _text(supplied, "Finalizer status: pending standard two-phase finalizer.")
    if supplied.strip():
        _status_summary_override(supplied, statuses, label="finalizer")
    summary = "Finalizer artifact status: " + "; ".join(statuses) + "."
    return summary


def _guard_summary(supplied: str, payload: Mapping[str, Any]) -> str:
    if not payload:
        return _text(supplied, "PR metadata guard: pending post-commit finalizer evidence.")
    status = _artifact_status(payload, label="PR metadata guard")
    if supplied.strip():
        _status_summary_override(supplied, (status,), label="PR metadata guard")
    reasons = payload.get("reasons", [])
    return f"PR metadata guard artifact status: {status}; reasons={json.dumps(reasons, sort_keys=True)}."


def _landing_gate_summary(supplied: str, payload: Mapping[str, Any]) -> str:
    if not payload:
        return _text(supplied, "Landing gate result: pending until scripts/codex_pr_landing_gate.py verifies this generated body.")
    decision = _artifact_status(payload, label="landing gate")
    if supplied.strip():
        _status_summary_override(supplied, (decision,), label="landing gate")
    blockers = payload.get("blocker_codes", [])
    warnings = payload.get("warning_codes", [])
    return f"Landing gate artifact decision: {decision}; blockers={json.dumps(blockers, sort_keys=True)}; warnings={json.dumps(warnings, sort_keys=True)}."


def _text(value: str, fallback: str) -> str:
    stripped = value.strip()
    return stripped if stripped else fallback


def build_body(
    *,
    title: str,
    intended_commit_title: str,
    matrix_json_path: Path | None,
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
    pre_commit_finalizer_json_path: str = "",
    pr_metadata_finalizer_json_path: str = "",
    pr_metadata_guard_json_path: str = "",
    landing_gate_json_path: str = "",
) -> str:
    supervisor = _load_optional_json_object(landing_supervisor_json_path)
    parsed_artifacts: dict[str, dict[str, Any]] = {}
    artifact_paths = {"pre_commit_finalizer": pre_commit_finalizer_json_path, "pr_metadata_finalizer": pr_metadata_finalizer_json_path, "pr_metadata_guard": pr_metadata_guard_json_path, "matrix": str(matrix_json_path) if matrix_json_path else "", "landing_gate": landing_gate_json_path, "landing_supervisor": landing_supervisor_json_path}
    missing_artifacts = [f"{key}:{value}" for key, value in artifact_paths.items() if value and not Path(value).exists()]
    if missing_artifacts:
        raise ValueError("artifact path does not exist: " + ", ".join(missing_artifacts))
    artifact_digests = {k: file_sha256(Path(v)) for k, v in artifact_paths.items() if v}
    for k, v in artifact_paths.items():
        if v:
            parsed_artifacts[k] = _load_json_object(Path(v), label=k)
    commit_binding = parsed_artifacts.get("pr_metadata_finalizer", {}).get("commit_binding", {})
    acceptance = parsed_artifacts.get("pr_metadata_finalizer", {}).get("task_acceptance")
    if any([pre_commit_finalizer_json_path, pr_metadata_finalizer_json_path, pr_metadata_guard_json_path]) and not isinstance(commit_binding, Mapping):
        raise ValueError("parsed finalizer artifacts missing commit binding")

    pre_payload = parsed_artifacts.get("pre_commit_finalizer", {})
    post_payload = parsed_artifacts.get("pr_metadata_finalizer", {})
    pre_plan = pre_payload.get("landing_validation_plan")
    post_plan = post_payload.get("landing_validation_plan")
    if not isinstance(post_plan, Mapping):
        raise ValueError("authoritative finalizer landing validation plan is required")
    hosted_verification_pending = False
    if isinstance(pre_plan, Mapping):
        pre_hosted = pre_plan.get("hosted_verification")
        post_hosted = post_plan.get("hosted_verification")
        hosted_verification_pending = (
            isinstance(pre_hosted, Mapping)
            and pre_hosted.get("status") == "pending"
            and isinstance(post_hosted, Mapping)
            and post_hosted.get("status") == "pending"
        )
        valid_transition, transition_reasons, _transition_proof = verify_validation_plan_transition(
            pre_plan, post_plan, pre_payload.get("workspace_binding", {}), commit_binding,
            pre_acceptance=pre_payload.get("task_acceptance"),
            post_acceptance=post_payload.get("task_acceptance"),
            hosted_verification_pending=hosted_verification_pending,
        )
        if not valid_transition:
            raise ValueError("invalid landing validation plan transition: " + ", ".join(transition_reasons))
    else:
        valid_plan, plan_reasons = verify_validation_plan(post_plan)
        if not valid_plan:
            raise ValueError("invalid authoritative landing validation plan: " + ", ".join(plan_reasons))
    plan: Mapping[str, Any] = post_plan
    validation_profile = str(plan.get("effective_profile"))
    matrix_status = str(plan.get("exhaustive_matrix_status"))
    if validation_profile == "solo":
        if matrix_status != SOLO_MATRIX_STATUS:
            raise ValueError("solo landing matrix disposition is contradictory")
        if matrix_json_path is not None:
            raise ValueError("solo landing must not supply exhaustive matrix evidence")
        matrix: dict[str, Any] = {}
    elif validation_profile == "exhaustive":
        if matrix_json_path is None or not matrix_json_path.exists():
            raise ValueError("exhaustive landing requires matrix-json-path")
        matrix = _load_json_object(matrix_json_path, label="matrix JSON")
        if str(matrix.get("status")) not in {"passed", "matrix_passed"} or int(matrix.get("required_failure_count", 1)) != 0:
            raise ValueError("exhaustive matrix evidence did not pass")
    else:
        raise ValueError("unsupported authoritative validation profile")

    status = str(matrix.get("status", "unknown"))
    required_failure_count = str(matrix.get("required_failure_count", "unknown"))
    command_count = str(matrix.get("command_count", len(_matrix_command_lines(matrix))))
    required_failures = matrix.get("required_failures", [])
    if not isinstance(required_failures, Sequence) or isinstance(required_failures, (str, bytes)):
        required_failures = []

    finalizer_payloads = (post_payload, pre_payload)
    targeted_mypy_result = _text(targeted_mypy, _stage_summary(matrix, finalizer_payloads, ("targeted_mypy",)))
    baseline_result = _text(baseline, _stage_summary(matrix, finalizer_payloads, ("mypy_baseline",)))
    docs_build_result = _text(docs_build, _stage_summary(matrix, finalizer_payloads, ("docs_build",)))
    prompt_boundary_result = _text(prompt_boundary, _stage_summary(matrix, finalizer_payloads, ("prompt_boundaries", "prompt_boundary")))
    strict_audit_result = _text(strict_audit, _stage_summary(matrix, finalizer_payloads, ("strict_audits", "strict_audit")))
    immutability_result = _text(immutability_verifier, _stage_summary(matrix, finalizer_payloads, ("audit_immutability", "immutability_verifier")))
    unresolved = _text(unresolved_risks, "None known.")

    matrix_lines = _matrix_command_lines(matrix)
    matrix_lines_text = "\n".join(matrix_lines) if matrix_lines else "- Matrix contained no per-command rows."
    path_text = str(matrix_json_path) if matrix_json_path else ""

    sections = [
        ("### Motivation", _text(motivation, "Motivation was not supplied to the evidence-body generator.")),
        ("### Description", _text(description, f"Title: {title}\nIntended commit title: {intended_commit_title}\nValidation profile: {validation_profile}\nCommit SHA: {commit_binding.get('head_sha', 'not bound') if isinstance(commit_binding, Mapping) else 'not bound'}\nTree SHA: {commit_binding.get('tree_sha', 'not bound') if isinstance(commit_binding, Mapping) else 'not bound'}\nParent/base SHA: {commit_binding.get('parent_sha', 'not bound') if isinstance(commit_binding, Mapping) else 'not bound'}\nChanged-path manifest digest: {commit_binding.get('changed_path_manifest_digest', 'not bound') if isinstance(commit_binding, Mapping) else 'not bound'}\nMatrix digest: {artifact_digests.get('matrix', 'not applicable')}\nArtifact digests: {json.dumps(artifact_digests, sort_keys=True)}")),
        ("### Testing", _text(testing, "See exact task acceptance and phase-finalizer checks below; the sealed solo plan did not request an exhaustive matrix." if validation_profile == "solo" else "See full matrix, targeted checks, landing gate, supervisor, finalizer, and PR metadata guard sections below.") + ("\n\nExact task acceptance: " + json.dumps(acceptance, sort_keys=True) if isinstance(acceptance, Mapping) else "")),
        ("### Targeted mypy", f"Targeted mypy result: {targeted_mypy_result}"),
        ("### Mypy baseline", f"Baseline result: {baseline_result}"),
        ("### Docs build", f"Docs build result: {docs_build_result}"),
        ("### Prompt-boundary verification", f"Prompt-boundary result: {prompt_boundary_result}"),
        ("### Strict audit", f"Strict audit result: {strict_audit_result}"),
        ("### Immutability verifier", f"Immutability verifier result: {immutability_result}"),
        ("### Landing gate", _landing_gate_summary(landing_gate, parsed_artifacts.get("landing_gate", {}))),
        ("### Landing Supervisor", _supervisor_summary(
            supervisor,
            landing_supervisor_json_path,
            validation_profile=validation_profile,
        )),
        ("### Finalizer status", _finalizer_summary(finalizer, pre_payload, post_payload)),
        ("### PR metadata guard", _guard_summary(pr_metadata_guard, parsed_artifacts.get("pr_metadata_guard", {}))),
        *([("### Hosted verification", "Required / Quality Gate is pending for strict_audits and audit_immutability. The PR may be submitted for hosted checks; `merge_permitted` is false until the exact required check passes under an enforced repository ruleset.")] if hosted_verification_pending else []),
        ("### Unresolved risks", f"Unresolved risks: {unresolved}"),
    ]
    if validation_profile == "exhaustive":
        matrix_sections = [
            ("### Full command matrix results", "\n".join([f"Full command matrix results: status={status}; required_failure_count={required_failure_count}; command_count={command_count}.", f"Required failures: {json.dumps(list(required_failures), sort_keys=True)}.", matrix_lines_text])),
            ("### Matrix runner summary", f"Matrix runner --summary result: {status}; required_failure_count={required_failure_count}."),
            ("### Matrix runner output", f"Matrix runner --output result/path: {path_text}\n{MATRIX_OUTPUT_PATH_PREFIX}{path_text}"),
        ]
    else:
        matrix_sections = [("### Exhaustive matrix disposition", f"Exhaustive matrix disposition: {matrix_status}.")]
    sections[3:3] = matrix_sections
    body = "\n\n".join(f"{heading}\n{content.strip()}" for heading, content in sections).strip() + "\n"
    validate_body(body, validation_profile=validation_profile, matrix_json_path=matrix_json_path)
    result = verify_pr_metadata(pr_title=title, pr_body=body, validation_profile=validation_profile, intended_commit_title=intended_commit_title)
    if result.status != "codex_pr_metadata_contract_ready":
        raise ValueError("generated body failed profile-aware PR metadata verification")
    return body


def validate_body(body: str, *, validation_profile: str, matrix_json_path: Path | None) -> None:
    normalized = " ".join(body.lower().replace("_", " ").split())
    if len(body.strip()) < 600:
        raise ValueError("generated body is evidence-light")
    required_sections = REQUIRED_SECTIONS if validation_profile == "exhaustive" else tuple(section for section in REQUIRED_SECTIONS if "matrix" not in section.lower()) + ("### Exhaustive matrix disposition",)
    missing_sections = [section for section in required_sections if section not in body]
    if missing_sections:
        raise ValueError("generated body omitted required sections: " + ", ".join(missing_sections))
    if validation_profile == "exhaustive" and MATRIX_OUTPUT_PATH_PREFIX + str(matrix_json_path) not in body:
        raise ValueError("generated body omitted Matrix output path marker")
    if "### Unresolved risks" not in body or "unresolved risks:" not in normalized:
        raise ValueError("generated body omitted unresolved risks section")
    required_markers = GUARD_REQUIRED_MARKERS if validation_profile == "exhaustive" else tuple(marker for marker in GUARD_REQUIRED_MARKERS if "matrix" not in marker) + ("validation profile: solo", "exhaustive matrix disposition: not requested for solo profile")
    missing_markers = [marker for marker in required_markers if marker not in normalized]
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
    parser.add_argument("--matrix-json-path", default="")
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
    parser.add_argument("--pre-commit-finalizer-json-path", default="")
    parser.add_argument("--pr-metadata-finalizer-json-path", default="")
    parser.add_argument("--pr-metadata-guard-json-path", default="")
    parser.add_argument("--landing-gate-json-path", default="")
    parser.add_argument("--sidecar-output", default="")
    parser.add_argument("--verify-body-binding", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    matrix_json_path = Path(args.matrix_json_path) if args.matrix_json_path.strip() else None
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
            pre_commit_finalizer_json_path=args.pre_commit_finalizer_json_path,
            pr_metadata_finalizer_json_path=args.pr_metadata_finalizer_json_path,
            pr_metadata_guard_json_path=args.pr_metadata_guard_json_path,
            landing_gate_json_path=args.landing_gate_json_path,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    Path(args.output).write_text(body, encoding="utf-8")
    if args.sidecar_output:
        artifacts = {k: v for k, v in {"pre_commit_finalizer": args.pre_commit_finalizer_json_path, "pr_metadata_finalizer": args.pr_metadata_finalizer_json_path, "pr_metadata_guard": args.pr_metadata_guard_json_path, "matrix": args.matrix_json_path, "landing_gate": args.landing_gate_json_path, "landing_supervisor": args.landing_supervisor_json_path}.items() if v}
        pr_payload = _load_json_object(Path(args.pr_metadata_finalizer_json_path), label="pr metadata finalizer") if args.pr_metadata_finalizer_json_path else {}
        commit = pr_payload.get("commit_binding", {}) if isinstance(pr_payload, Mapping) else {}
        sidecar = create_body_binding(args.title, args.output, commit, artifacts).to_dict()
        Path(args.sidecar_output).write_text(json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8")
        result = verify_body_binding(args.title, args.output, sidecar, artifacts)
        if args.verify_body_binding:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
            return 0 if result.status == "pr_body_binding_ready" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
