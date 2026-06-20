from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

READY = "codex_lifecycle_ready"
INCOMPLETE = "codex_lifecycle_incomplete"
BLOCKED = "codex_lifecycle_blocked"
GUARD_READY = "pr_metadata_guard_ready"
GUARD_NOT_PROVIDED = "not_provided"

NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "summary_does_not_bypass_finalizer": True,
    "summary_does_not_bypass_pr_metadata_guard": True,
    "summary_does_not_authorize_pr_creation": True,
    "summary_does_not_authorize_dirty_source_files": True,
    "summary_does_not_grant_runtime_authority": True,
}

OPTIONAL_FRESHNESS_FIELDS = (
    "terminal_refresh_status",
    "rerun_required",
    "stale_evidence_refresh_result",
    "cleanup_occurred",
    "terminal_cleanup_occurred",
    "cleaned_paths",
    "terminal_cleaned_paths",
    "refresh_stage_runs",
    "refresh_stages_ran",
    "refreshed_matrix_json_path",
)


class CodexTaskLifecycleSummaryError(ValueError):
    """Raised when required lifecycle evidence cannot be summarized safely."""


@dataclass(frozen=True)
class CodexTaskLifecycleSummaryRequest:
    title: str
    intended_commit_title: str
    pre_commit_finalizer_json: str
    pr_metadata_finalizer_json: str
    matrix_json_path: str
    output: str = ""
    pr_metadata_guard_json: str | None = None
    task_id: str | None = None


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\u241f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _load_json_object(path_text: str, label: str) -> dict[str, Any]:
    path = Path(path_text)
    if not path.exists():
        raise CodexTaskLifecycleSummaryError(f"{label}_missing:{path_text}")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CodexTaskLifecycleSummaryError(f"{label}_invalid_json:{path_text}:{exc.msg}") from exc
    if not isinstance(loaded, dict):
        raise CodexTaskLifecycleSummaryError(f"{label}_json_not_object:{path_text}")
    return loaded


def _decision_status(payload: Mapping[str, Any], label: str) -> str:
    decision = payload.get("decision")
    if not isinstance(decision, Mapping):
        raise CodexTaskLifecycleSummaryError(f"{label}_missing_finalizer_decision")
    status = decision.get("status")
    if not isinstance(status, str) or not status:
        raise CodexTaskLifecycleSummaryError(f"{label}_missing_finalizer_status")
    return status


def _guard_status(payload: Mapping[str, Any]) -> str:
    status = payload.get("status")
    if isinstance(status, str) and status:
        return status
    raise CodexTaskLifecycleSummaryError("pr_metadata_guard_missing_status")


def _freshness_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    freshness = payload.get("evidence_freshness")
    if not isinstance(freshness, Mapping):
        freshness = {}
    return {field: freshness.get(field) for field in OPTIONAL_FRESHNESS_FIELDS}


def _finalizer_section(path: str, payload: Mapping[str, Any], label: str) -> dict[str, Any]:
    section = {"path": path, "status": _decision_status(payload, label)}
    section.update(_freshness_summary(payload))
    return section


def build_task_lifecycle_summary(request: CodexTaskLifecycleSummaryRequest) -> dict[str, Any]:
    task_id = request.task_id or _stable_id("task", request.title, request.intended_commit_title)
    pre_payload = _load_json_object(request.pre_commit_finalizer_json, "pre_commit_finalizer_json")
    pr_payload = _load_json_object(request.pr_metadata_finalizer_json, "pr_metadata_finalizer_json")
    pre = _finalizer_section(request.pre_commit_finalizer_json, pre_payload, "pre_commit_finalizer")
    pr = _finalizer_section(request.pr_metadata_finalizer_json, pr_payload, "pr_metadata_finalizer")

    guard_status = GUARD_NOT_PROVIDED
    guard_path: str | None = None
    if request.pr_metadata_guard_json:
        guard_path = request.pr_metadata_guard_json
        guard_status = _guard_status(_load_json_object(request.pr_metadata_guard_json, "pr_metadata_guard_json"))

    reasons: list[str] = []
    missing_required = False
    if pre["status"] != "ready_to_commit":
        reasons.append(f"pre_commit_finalizer_not_ready:{pre['status']}")
    if pr["status"] != "ready_for_pr_metadata":
        reasons.append(f"pr_metadata_finalizer_not_ready:{pr['status']}")
    for label, section in (("pre_commit", pre), ("pr_metadata", pr)):
        if section.get("rerun_required") is True:
            reasons.append(f"{label}_finalizer_rerun_required")
    if guard_status not in {GUARD_NOT_PROVIDED, GUARD_READY}:
        reasons.append(f"pr_metadata_guard_not_ready:{guard_status}")

    overall = INCOMPLETE if missing_required else (BLOCKED if reasons else READY)
    rerun_required = bool(reasons or missing_required)

    summary: dict[str, Any] = {
        "summary_id": _stable_id("codex_task_lifecycle_summary", task_id, request.title, request.intended_commit_title, request.matrix_json_path),
        "task_id": task_id,
        "title": request.title,
        "intended_commit_title": request.intended_commit_title,
        "matrix_json_path": request.matrix_json_path,
        "pre_commit_finalizer_status": pre["status"],
        "pr_metadata_finalizer_status": pr["status"],
        "pr_metadata_guard_status": guard_status,
        "pr_metadata_guard_json_path": guard_path,
        "finalizers": {"pre_commit": pre, "pr_metadata": pr},
        "overall_lifecycle_status": overall,
        "rerun_required": rerun_required,
        "rerun_reason": ";".join(reasons) if rerun_required else None,
        "metadata_only": True,
        "developer_workflow_evidence_only": True,
        "non_authority_posture": dict(NON_AUTHORITY_POSTURE),
    }
    return summary


def write_task_lifecycle_summary(summary: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
