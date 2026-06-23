from __future__ import annotations

import hashlib
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
    doctrine_map_json: str | None = None


def _omitted_input_provenance() -> dict[str, Any]:
    return {
        "provided": False,
        "path": None,
        "exists": False,
        "readable_json": False,
        "digest_algo": "sha256",
        "digest": None,
        "byte_size": None,
        "error": None,
    }


def _load_json_object_with_provenance(path_text: str, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_text)
    provenance: dict[str, Any] = {
        "provided": True,
        "path": path_text,
        "exists": path.exists(),
        "readable_json": False,
        "digest_algo": "sha256",
        "digest": None,
        "byte_size": None,
        "error": None,
    }
    if not path.exists():
        provenance["error"] = f"{label}_missing"
        raise CodexLandingEvidenceAppendixError(f"{label}_missing:{path_text}")
    raw = path.read_bytes()
    provenance["digest"] = hashlib.sha256(raw).hexdigest()
    provenance["byte_size"] = len(raw)
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        provenance["error"] = f"{label}_invalid_utf8"
        raise CodexLandingEvidenceAppendixError(f"{label}_invalid_utf8:{path_text}:{exc.reason}") from exc
    except json.JSONDecodeError as exc:
        provenance["error"] = f"{label}_invalid_json"
        raise CodexLandingEvidenceAppendixError(f"{label}_invalid_json:{path_text}:{exc.msg}") from exc
    if not isinstance(loaded, dict):
        provenance["error"] = f"{label}_json_not_object"
        raise CodexLandingEvidenceAppendixError(f"{label}_json_not_object:{path_text}")
    provenance["readable_json"] = True
    return loaded, provenance


def _load_json_object(path_text: str, label: str) -> dict[str, Any]:
    loaded, _provenance = _load_json_object_with_provenance(path_text, label)
    return loaded


def _markdown_output_provenance(markdown: str, output: str | None, json_output: str | None) -> dict[str, Any]:
    raw = markdown.encode("utf-8")
    return {
        "markdown_output_path": output,
        "markdown_digest_algo": "sha256",
        "markdown_digest": hashlib.sha256(raw).hexdigest(),
        "markdown_byte_size": len(raw),
        "json_sidecar_output_path": json_output,
        "json_sidecar_digest_algo": None,
        "json_sidecar_digest": None,
        "json_sidecar_byte_size": None,
        "json_sidecar_self_digest_note": "Intentionally omitted to avoid embedding an unstable digest of the sidecar inside itself.",
    }


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


def _doctrine_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _truthy_mapping_flags(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
    return all(mapping.get(key) is True for key in keys)


def _render_doctrine(lines: list[str], doctrine: Mapping[str, Any] | None) -> None:
    lines.append("## Beneficial Trait Doctrine")
    if doctrine is None:
        lines.append("Beneficial trait doctrine map JSON was not provided; no doctrine tables were rendered.")
        lines.append("The appendix remains review context only and does not use doctrine as readiness authority.")
        lines.append("")
        return

    posture = _as_mapping(doctrine.get("non_authority_posture"))
    lines.append("### Doctrine posture")
    for key in ("metadata_only", "doctrine_only", "not_model_training", "not_reinforcement_learning"):
        _kv(lines, key, doctrine.get(key))
    for key in sorted(posture):
        _kv(lines, key, posture[key])
    lines.append("")

    lines.append("### Trait catalog summary")
    lines.append("| trait_id | short definition |")
    lines.append("| --- | --- |")
    trait_catalog = _as_mapping(doctrine.get("trait_catalog"))
    for trait_id in sorted(str(key) for key in trait_catalog):
        lines.append(f"| {_cell(trait_id)} | {_cell(trait_catalog.get(trait_id))} |")
    lines.append("")

    lines.append("### Rail-to-trait summary")
    lines.append("| rail_id | rail_name | enforced_traits | reviewer_summary |")
    lines.append("| --- | --- | --- | --- |")
    rails = [_as_mapping(item) for item in _doctrine_list(doctrine.get("rail_mappings"))]
    for rail in sorted(rails, key=lambda item: _display(item.get("rail_id"))):
        row = [rail.get("rail_id"), rail.get("rail_name"), rail.get("enforced_traits"), rail.get("reviewer_summary")]
        lines.append("| " + " | ".join(_cell(value) for value in row) + " |")
    lines.append("")

    lines.append("### Trait-to-rails index")
    lines.append("| trait_id | rails |")
    lines.append("| --- | --- |")
    trait_to_rails = _as_mapping(doctrine.get("trait_to_rails_index"))
    for trait_id in sorted(str(key) for key in trait_to_rails):
        lines.append(f"| {_cell(trait_id)} | {_cell(trait_to_rails.get(trait_id))} |")
    lines.append("")

    lines.append("### Doctrine boundary")
    lines.append("- doctrine map explains existing rails")
    lines.append("- doctrine map does not decide readiness")
    lines.append("- doctrine map does not authorize commit")
    lines.append("- doctrine map does not authorize PR creation")
    lines.append("- doctrine map does not train or modify models")
    lines.append("")


def _doctrine_metadata(request: CodexLandingEvidenceAppendixRequest, doctrine: Mapping[str, Any] | None) -> dict[str, Any]:
    trait_catalog = _as_mapping(doctrine.get("trait_catalog")) if doctrine is not None else {}
    rails = [_as_mapping(item) for item in _doctrine_list(doctrine.get("rail_mappings"))] if doctrine is not None else []
    posture = _as_mapping(doctrine.get("non_authority_posture")) if doctrine is not None else {}
    return {
        "appendix_does_not_use_doctrine_as_authority": True,
        "appendix_renders_doctrine_as_review_context_only": True,
        "doctrine_map_id": doctrine.get("doctrine_map_id") if doctrine is not None else None,
        "doctrine_map_json_path": request.doctrine_map_json,
        "doctrine_non_authority_posture_seen": _truthy_mapping_flags(
            posture,
            (
                "doctrine_map_does_not_decide_readiness",
                "doctrine_map_does_not_authorize_commit",
                "doctrine_map_does_not_authorize_pr_creation",
                "doctrine_map_does_not_train_or_modify_models",
            ),
        ),
        "doctrine_rail_mapping_count": len(rails),
        "doctrine_rails_rendered": [_display(rail.get("rail_id")) for rail in sorted(rails, key=lambda item: _display(item.get("rail_id")))],
        "doctrine_trait_count": len(trait_catalog),
        "doctrine_traits_rendered": sorted(str(key) for key in trait_catalog),
    }


def _render_test_provenance(lines: list[str], index: Mapping[str, Any] | None, doctor: Mapping[str, Any] | None) -> None:
    hints = _as_mapping(index.get("aggregate_hints")) if index is not None else {}
    provenance = _as_mapping(_doctor_summary(doctor, "test_provenance_summary"))
    lines.append("## Test provenance summary")
    for key in ("run_intent", "execution_mode", "tests_selected", "tests_executed", "tests_passed", "tests_skipped"):
        _kv(lines, key, provenance.get(key))
    _kv(lines, "exit_reason", provenance.get("exit_reason", hints.get("test_provenance_exit_reason")))
    lines.append("")


def build_landing_evidence_appendix(request: CodexLandingEvidenceAppendixRequest) -> tuple[str, dict[str, Any]]:
    input_provenance = {
        "evidence_index_json": _omitted_input_provenance(),
        "doctor_report_json": _omitted_input_provenance(),
        "doctrine_map_json": _omitted_input_provenance(),
    }
    index = None
    doctor = None
    doctrine = None
    if request.evidence_index_json:
        index, input_provenance["evidence_index_json"] = _load_json_object_with_provenance(request.evidence_index_json, "evidence_index_json")
    if request.doctor_report_json:
        doctor, input_provenance["doctor_report_json"] = _load_json_object_with_provenance(request.doctor_report_json, "doctor_report_json")
    if request.doctrine_map_json:
        doctrine, input_provenance["doctrine_map_json"] = _load_json_object_with_provenance(request.doctrine_map_json, "doctrine_map_json")
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
    _render_doctrine(lines, doctrine)
    lines.append("## Non-authority posture")
    for key in sorted(NON_AUTHORITY_POSTURE):
        _kv(lines, key, NON_AUTHORITY_POSTURE[key])
    lines.append("")
    markdown = "\n".join(lines)
    metadata = {
        "appendix_is_non_authoritative": True,
        "provenance_digest_version": 1,
        "input_provenance": input_provenance,
        "output_provenance": _markdown_output_provenance(markdown, request.output, request.json_output),
        "appendix_provenance_is_metadata_only": True,
        "appendix_provenance_is_read_only": True,
        "appendix_provenance_does_not_verify_authority": True,
        "appendix_provenance_does_not_decide_readiness": True,
        "appendix_provenance_does_not_authorize_commit": True,
        "appendix_provenance_does_not_authorize_pr_creation": True,
        "doctor_report_id": doctor.get("doctor_report_id") if doctor is not None else None,
        "doctor_report_provided": doctor is not None,
        "evidence_index_id": index.get("evidence_index_id") if index is not None else None,
        "evidence_index_provided": index is not None,
        "intended_commit_title": request.intended_commit_title,
        "non_authority_posture": dict(NON_AUTHORITY_POSTURE),
        "output": request.output,
        "title": request.title,
        **_doctrine_metadata(request, doctrine),
    }
    return markdown, metadata


def write_landing_evidence_appendix(markdown: str, output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown, encoding="utf-8")


def write_landing_evidence_appendix_metadata(metadata: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
