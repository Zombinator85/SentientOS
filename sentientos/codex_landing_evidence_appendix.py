from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "appendix_is_read_only": True,
    "appendix_does_not_rerun_commands": True,
    "appendix_does_not_decide_readiness": True,
    "appendix_does_not_bypass_finalizer": True,
    "appendix_does_not_bypass_pr_metadata_guard": True,
    "appendix_does_not_authorize_commit": True,
    "appendix_does_not_authorize_pr_creation": True,
    "appendix_does_not_authorize_runtime_action": True,
}


class CodexLandingEvidenceAppendixError(ValueError):
    """Raised when appendix input evidence cannot be read as a JSON object."""


@dataclass(frozen=True)
class CodexLandingEvidenceAppendixRequest:
    title: str
    intended_commit_title: str
    output: str | None = None
    evidence_index_json: str | None = None
    doctor_report_json: str | None = None
    json_output: str | None = None


def _load_json_object(path_text: str, label: str) -> dict[str, Any]:
    path = Path(path_text)
    if not path.exists():
        raise CodexLandingEvidenceAppendixError(f"{label}_missing:{path_text}")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CodexLandingEvidenceAppendixError(f"{label}_invalid_json:{path_text}:{exc.msg}") from exc
    if not isinstance(loaded, dict):
        raise CodexLandingEvidenceAppendixError(f"{label}_json_not_object:{path_text}")
    return loaded


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _display(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return value if value else "unavailable"
    if isinstance(value, list):
        return "none" if not value else ", ".join(_display(item) for item in value)
    if isinstance(value, Mapping):
        return "none" if not value else ", ".join(f"{key}={_display(value[key])}" for key in sorted(value))
    return str(value)


def _cell(value: Any) -> str:
    return _display(value).replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")


def _short_digest(value: Any) -> str:
    digest = _display(value)
    if digest == "unavailable":
        return digest
    if digest.startswith("sha256:"):
        return "sha256:" + digest.removeprefix("sha256:")[:12]
    return digest[:12]


def _kv(lines: list[str], key: str, value: Any) -> None:
    lines.append(f"- **{key}:** {_cell(value)}")


def _doctor_summary(doctor: Mapping[str, Any] | None, key: str) -> Any:
    return _as_mapping(doctor).get(key) if doctor is not None else None


def _render_index(lines: list[str], index: Mapping[str, Any] | None) -> None:
    lines.append("## Evidence index summary")
    if index is None:
        lines.append("Evidence index JSON was not provided.")
        lines.append("")
        lines.append("## Artifact table")
        lines.append("Evidence index JSON was not provided.")
        lines.append("")
        return
    _kv(lines, "evidence_index_id", index.get("evidence_index_id"))
    _kv(lines, "artifact_count", index.get("artifact_count"))
    _kv(lines, "artifact_roles_present", index.get("artifact_roles_present"))
    _kv(lines, "artifact_roles_missing", index.get("artifact_roles_missing"))
    _kv(lines, "aggregate_hints", index.get("aggregate_hints"))
    lines.append("")
    lines.append("## Artifact table")
    lines.append("| role | path | exists | readable_json | digest | status_hint | schema_hint | error |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    artifacts = [_as_mapping(item) for item in _as_list(index.get("artifacts"))]
    for artifact in sorted(artifacts, key=lambda item: _display(item.get("role"))):
        row = [
            artifact.get("role"),
            artifact.get("path"),
            artifact.get("exists"),
            artifact.get("readable_json"),
            _short_digest(artifact.get("digest")),
            artifact.get("status_hint"),
            artifact.get("schema_hint"),
            artifact.get("error"),
        ]
        lines.append("| " + " | ".join(_cell(value) for value in row) + " |")
    lines.append("")


def _render_doctor(lines: list[str], doctor: Mapping[str, Any] | None) -> None:
    lines.append("## Lifecycle doctor summary")
    if doctor is None:
        lines.append("Lifecycle doctor report JSON was not provided.")
        lines.append("")
        return
    for key in ("doctor_report_id", "overall_doctor_status", "readiness_summary", "next_safe_action", "next_safe_action_reason", "missing_evidence"):
        _kv(lines, key, doctor.get(key))
    lines.append("")


def _render_matrix(lines: list[str], index: Mapping[str, Any] | None, doctor: Mapping[str, Any] | None) -> None:
    hints = _as_mapping(index.get("aggregate_hints")) if index is not None else {}
    matrix = _as_mapping(_doctor_summary(doctor, "matrix_summary"))
    source = matrix or hints
    lines.append("## Matrix proof summary")
    for key in ("required_failure_count", "nonproof_count", "diagnostic_failure_count", "blocked_lane_count"):
        _kv(lines, key, source.get(key))
    lines.append("")


def _render_finalizer(lines: list[str], index: Mapping[str, Any] | None, doctor: Mapping[str, Any] | None) -> None:
    hints = _as_mapping(index.get("aggregate_hints")) if index is not None else {}
    finalizer = _as_mapping(_doctor_summary(doctor, "finalizer_summary"))
    guard = _as_mapping(_doctor_summary(doctor, "pr_metadata_guard_summary"))
    lines.append("## Finalizer / guard summary")
    _kv(lines, "pre_commit_finalizer_status", finalizer.get("pre_commit_status", hints.get("pre_commit_finalizer_status")))
    _kv(lines, "pr_metadata_finalizer_status", finalizer.get("pr_metadata_status", hints.get("pr_metadata_finalizer_status")))
    _kv(lines, "pr_metadata_guard_status", guard.get("status", hints.get("pr_metadata_guard_status")))
    _kv(lines, "rerun_required", finalizer.get("rerun_required"))
    _kv(lines, "terminal_refresh_status", finalizer.get("terminal_refresh_status"))
    lines.append("")


def _render_test_provenance(lines: list[str], index: Mapping[str, Any] | None, doctor: Mapping[str, Any] | None) -> None:
    hints = _as_mapping(index.get("aggregate_hints")) if index is not None else {}
    provenance = _as_mapping(_doctor_summary(doctor, "test_provenance_summary"))
    lines.append("## Test provenance summary")
    for key in ("run_intent", "execution_mode", "tests_selected", "tests_executed", "tests_passed", "tests_skipped"):
        _kv(lines, key, provenance.get(key))
    _kv(lines, "exit_reason", provenance.get("exit_reason", hints.get("test_provenance_exit_reason")))
    lines.append("")


def build_landing_evidence_appendix(request: CodexLandingEvidenceAppendixRequest) -> tuple[str, dict[str, Any]]:
    index = _load_json_object(request.evidence_index_json, "evidence_index_json") if request.evidence_index_json else None
    doctor = _load_json_object(request.doctor_report_json, "doctor_report_json") if request.doctor_report_json else None
    lines = [
        "# Codex Landing Evidence Appendix",
        "",
        f"- **Task title:** {_cell(request.title)}",
        f"- **Intended commit title:** {_cell(request.intended_commit_title)}",
        "",
        "## Evidence posture",
        "- metadata-only",
        "- read-only",
        "- non-authoritative",
        "- does not grant commit authority",
        "- does not grant PR creation authority",
        "",
    ]
    _render_index(lines, index)
    _render_doctor(lines, doctor)
    _render_matrix(lines, index, doctor)
    _render_finalizer(lines, index, doctor)
    _render_test_provenance(lines, index, doctor)
    lines.append("## Non-authority posture")
    for key in sorted(NON_AUTHORITY_POSTURE):
        _kv(lines, key, NON_AUTHORITY_POSTURE[key])
    lines.append("")
    metadata = {
        "appendix_is_non_authoritative": True,
        "doctor_report_id": doctor.get("doctor_report_id") if doctor is not None else None,
        "doctor_report_provided": doctor is not None,
        "evidence_index_id": index.get("evidence_index_id") if index is not None else None,
        "evidence_index_provided": index is not None,
        "intended_commit_title": request.intended_commit_title,
        "non_authority_posture": dict(NON_AUTHORITY_POSTURE),
        "output": request.output,
        "title": request.title,
    }
    return "\n".join(lines), metadata


def write_landing_evidence_appendix(markdown: str, output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown, encoding="utf-8")


def write_landing_evidence_appendix_metadata(metadata: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
