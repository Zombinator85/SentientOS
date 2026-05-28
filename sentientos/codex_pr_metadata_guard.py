from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

READY_STATUS = "pr_metadata_guard_ready"
SOURCE_DOC_TEST_PREFIXES = ("sentientos/", "scripts/", "tests/", "docs/", "api/")
SOURCE_DOC_TEST_SUFFIXES = (".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".bat")
NONBLOCKING_STALE_RESULTS = {"not_required", "succeeded"}
CLEAN_CLASSIFICATIONS = {"clean"}
PASSING_LANDING_GATE_STATUSES = {"passed", "ready", "ok"}
PASSING_SUPERVISOR_STATUSES = {"ready_for_pr_metadata", "passed", "ready"}


@dataclass(frozen=True)
class CodexPrMetadataGuardRequest:
    title: str
    intended_commit_title: str
    pre_commit_finalizer_json: str = ""
    pr_metadata_finalizer_json: str = ""
    matrix_json_path: str = ""
    validation_only: bool = False
    workspace_root: str = "."
    git_status_lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class CodexPrMetadataGuardResult:
    status: str
    ready: bool
    reasons: tuple[str, ...]
    proof: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_json(path_text: str) -> tuple[dict[str, Any] | None, str]:
    if not path_text:
        return None, "path_not_provided"
    path = Path(path_text)
    if not path.exists():
        return None, "path_missing"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, "invalid_json"
    if not isinstance(loaded, dict):
        return None, "json_not_object"
    return loaded, "loaded"


def _decision_status(payload: Mapping[str, Any] | None) -> str:
    decision = payload.get("decision") if payload else None
    if isinstance(decision, Mapping):
        return str(decision.get("status", ""))
    return ""


def _request_value(payload: Mapping[str, Any] | None, key: str) -> str:
    request = payload.get("request") if payload else None
    if isinstance(request, Mapping):
        return str(request.get(key, ""))
    return ""


def _command_exit(payload: Mapping[str, Any] | None, stage: str) -> int | None:
    if not payload:
        return None
    report = payload.get("report")
    commands = report.get("commands") if isinstance(report, Mapping) else None
    if not isinstance(commands, Sequence) or isinstance(commands, (str, bytes)):
        return None
    matches: list[int] = []
    for item in commands:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("stage", "")) == stage or str(item.get("stage", "")).startswith(f"stale_evidence_{stage}"):
            try:
                matches.append(int(item.get("exit_code", 1)))
            except (TypeError, ValueError):
                matches.append(1)
    if not matches:
        return None
    return matches[-1]


def _embedded_status(payload: Mapping[str, Any] | None, keys: tuple[str, ...]) -> str:
    if not payload:
        return ""
    stack: list[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            for key in keys:
                value = current.get(key)
                if isinstance(value, str):
                    return value
            stack.extend(current.values())
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
            stack.extend(current)
    return ""


def _matrix_passed(payload: Mapping[str, Any] | None) -> bool:
    return bool(payload and str(payload.get("status", "")) == "passed" and int(payload.get("required_failure_count", 1)) == 0)


def _has_source_doc_test_changes(lines: tuple[str, ...]) -> bool:
    for line in lines:
        path = line[3:] if len(line) > 3 else line
        if path.startswith(SOURCE_DOC_TEST_PREFIXES) and path.endswith(SOURCE_DOC_TEST_SUFFIXES):
            return True
    return False


def _git_status_lines(workspace_root: str) -> tuple[str, ...]:
    completed = subprocess.run(["git", "status", "--short"], cwd=workspace_root, check=False, capture_output=True, text=True)
    return tuple(line.rstrip() for line in completed.stdout.splitlines() if line.strip())


def _dirty_tree_clean(payload: Mapping[str, Any] | None) -> bool:
    if not payload:
        return False
    artifacts = payload.get("report", {}).get("artifacts") if isinstance(payload.get("report"), Mapping) else None
    if isinstance(artifacts, Sequence) and not isinstance(artifacts, (str, bytes)):
        classifications = [str(item.get("classification", "")) for item in artifacts if isinstance(item, Mapping)]
        if classifications and all(item in CLEAN_CLASSIFICATIONS for item in classifications):
            return True
        if any(item not in CLEAN_CLASSIFICATIONS for item in classifications):
            return False
    dirty_paths = payload.get("dirty_paths")
    if isinstance(dirty_paths, Sequence) and not isinstance(dirty_paths, (str, bytes)):
        return len(dirty_paths) == 0
    return True


def evaluate_pr_metadata_guard(request: CodexPrMetadataGuardRequest) -> CodexPrMetadataGuardResult:
    reasons: list[str] = []
    proof: dict[str, Any] = {
        "title": request.title,
        "intended_commit_title": request.intended_commit_title,
        "validation_only": request.validation_only,
    }

    if request.title != request.intended_commit_title:
        reasons.append("title_mismatch:cli")

    pre_payload: dict[str, Any] | None = None
    pre_load = "not_required_validation_only" if request.validation_only and not request.pre_commit_finalizer_json else "path_not_provided"
    if not request.validation_only or request.pre_commit_finalizer_json:
        pre_payload, pre_load = _load_json(request.pre_commit_finalizer_json)
    proof["pre_commit_finalizer"] = {"path": request.pre_commit_finalizer_json, "load_status": pre_load, "decision": _decision_status(pre_payload)}

    pr_payload, pr_load = _load_json(request.pr_metadata_finalizer_json)
    proof["pr_metadata_finalizer"] = {"path": request.pr_metadata_finalizer_json, "load_status": pr_load, "decision": _decision_status(pr_payload)}

    matrix_payload, matrix_load = _load_json(request.matrix_json_path)
    proof["matrix"] = {"path": request.matrix_json_path, "load_status": matrix_load, "status": str(matrix_payload.get("status", "")) if matrix_payload else ""}

    if request.validation_only:
        lines = request.git_status_lines or _git_status_lines(request.workspace_root)
        proof["validation_only_git_status"] = list(lines)
        if _has_source_doc_test_changes(lines):
            reasons.append("validation_only_source_doc_test_changes_present")
    elif pre_payload is None:
        reasons.append("missing_pre_commit_finalizer")

    if pr_payload is None:
        reasons.append("missing_pr_metadata_finalizer")

    if pre_payload is not None:
        if _decision_status(pre_payload) != "ready_to_commit":
            reasons.append(f"pre_commit_decision_not_ready:{_decision_status(pre_payload) or 'missing'}")
        if _request_value(pre_payload, "title") and _request_value(pre_payload, "title") != request.title:
            reasons.append("title_mismatch:pre_commit_title")
        if _request_value(pre_payload, "intended_commit_title") and _request_value(pre_payload, "intended_commit_title") != request.intended_commit_title:
            reasons.append("title_mismatch:pre_commit_intended_commit_title")

    if pr_payload is not None:
        if _decision_status(pr_payload) != "ready_for_pr_metadata":
            reasons.append(f"pr_metadata_decision_not_ready:{_decision_status(pr_payload) or 'missing'}")
        if _request_value(pr_payload, "title") and _request_value(pr_payload, "title") != request.title:
            reasons.append("title_mismatch:pr_metadata_title")
        if _request_value(pr_payload, "intended_commit_title") and _request_value(pr_payload, "intended_commit_title") != request.intended_commit_title:
            reasons.append("title_mismatch:pr_metadata_intended_commit_title")
        freshness = pr_payload.get("evidence_freshness")
        stale_result = str(freshness.get("stale_evidence_refresh_result", "not_required")) if isinstance(freshness, Mapping) else "not_required"
        proof["stale_evidence_refresh_result"] = stale_result
        if stale_result not in NONBLOCKING_STALE_RESULTS:
            reasons.append(f"stale_evidence_refresh_not_ready:{stale_result}")
        if not _dirty_tree_clean(pr_payload):
            reasons.append("dirty_tree_not_clean")
        gate_exit = _command_exit(pr_payload, "pr_landing_gate")
        gate_status = _embedded_status(pr_payload, ("landing_gate_status", "pr_landing_gate_status"))
        proof["pr_landing_gate"] = {"exit_code": gate_exit, "status": gate_status}
        if gate_exit not in (0, None) or (gate_exit is None and gate_status not in PASSING_LANDING_GATE_STATUSES):
            reasons.append("pr_landing_gate_not_passed")
        supervisor_exit = _command_exit(pr_payload, "landing_supervisor")
        supervisor_status = _embedded_status(pr_payload, ("landing_supervisor_status", "supervisor_status"))
        proof["landing_supervisor"] = {"exit_code": supervisor_exit, "status": supervisor_status}
        if supervisor_exit not in (0, None) or (supervisor_exit is None and supervisor_status not in PASSING_SUPERVISOR_STATUSES):
            reasons.append("landing_supervisor_not_ready")

    if not _matrix_passed(matrix_payload):
        reasons.append("matrix_not_passed")

    status = _status_for_reasons(tuple(reasons))
    return CodexPrMetadataGuardResult(status=status, ready=status == READY_STATUS, reasons=tuple(reasons), proof=proof)


def _status_for_reasons(reasons: tuple[str, ...]) -> str:
    if not reasons:
        return READY_STATUS
    if any(reason.startswith("missing_pre_commit_finalizer") for reason in reasons):
        return "pr_metadata_guard_blocked_missing_pre_commit_finalizer"
    if any(reason.startswith("missing_pr_metadata_finalizer") for reason in reasons):
        return "pr_metadata_guard_blocked_missing_pr_metadata_finalizer"
    if any(reason.startswith("pre_commit_decision_not_ready") for reason in reasons):
        return "pr_metadata_guard_blocked_pre_commit_not_ready"
    if any(reason.startswith("pr_metadata_decision_not_ready") for reason in reasons):
        return "pr_metadata_guard_blocked_pr_metadata_not_ready"
    if any(reason.startswith("title_mismatch") for reason in reasons):
        return "pr_metadata_guard_blocked_title_mismatch"
    if any(reason.startswith("matrix_not_passed") for reason in reasons):
        return "pr_metadata_guard_blocked_matrix_failed"
    if any(reason.startswith("stale_evidence_refresh_not_ready") for reason in reasons):
        return "pr_metadata_guard_blocked_stale_evidence"
    if any(reason.startswith("dirty_tree_not_clean") for reason in reasons):
        return "pr_metadata_guard_blocked_dirty_tree"
    if any(reason.startswith("validation_only_") for reason in reasons):
        return "pr_metadata_guard_blocked_validation_only_mismatch"
    return "pr_metadata_guard_failed"


def result_json(result: CodexPrMetadataGuardResult) -> str:
    return json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n"
