from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

DIGEST_ALGO = "sha256"
CREATED_AT = "deterministic-input-digest"

ARTIFACT_ROLES: tuple[str, ...] = (
    "matrix",
    "pre_commit_finalizer",
    "pr_metadata_finalizer",
    "pr_metadata_guard",
    "lifecycle_summary",
    "doctor_report",
    "test_provenance",
)

NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "index_is_read_only": True,
    "index_does_not_rerun_commands": True,
    "index_does_not_decide_readiness": True,
    "index_does_not_bypass_finalizer": True,
    "index_does_not_bypass_pr_metadata_guard": True,
    "index_does_not_authorize_commit": True,
    "index_does_not_authorize_pr_creation": True,
    "index_does_not_authorize_runtime_action": True,
}


@dataclass(frozen=True)
class CodexLandingEvidenceIndexRequest:
    title: str
    intended_commit_title: str
    output: str | None = None
    matrix_json_path: str | None = None
    pre_commit_finalizer_json: str | None = None
    pr_metadata_finalizer_json: str | None = None
    pr_metadata_guard_json: str | None = None
    lifecycle_summary_json: str | None = None
    doctor_report_json: str | None = None
    test_provenance_json: str | None = None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{prefix}_{_sha256(encoded)[:16]}"


def _role_paths(request: CodexLandingEvidenceIndexRequest) -> dict[str, str | None]:
    return {
        "matrix": request.matrix_json_path,
        "pre_commit_finalizer": request.pre_commit_finalizer_json,
        "pr_metadata_finalizer": request.pr_metadata_finalizer_json,
        "pr_metadata_guard": request.pr_metadata_guard_json,
        "lifecycle_summary": request.lifecycle_summary_json,
        "doctor_report": request.doctor_report_json,
        "test_provenance": request.test_provenance_json,
    }


def _finalizer_status(payload: Mapping[str, Any]) -> str | None:
    decision = payload.get("decision")
    if isinstance(decision, Mapping) and isinstance(decision.get("status"), str):
        return str(decision["status"])
    status = payload.get("status")
    return str(status) if isinstance(status, str) else None


def _schema_hint(role: str, payload: Mapping[str, Any] | None) -> str | None:
    if payload is None:
        return None
    if role == "matrix" and "results" in payload:
        return "work_item_review_packet_matrix"
    if role in {"pre_commit_finalizer", "pr_metadata_finalizer"} and ("decision" in payload or "evidence_freshness" in payload):
        return "codex_finalize_landing"
    if role == "pr_metadata_guard" and "status" in payload:
        return "codex_pr_metadata_guard"
    if role == "lifecycle_summary" and "overall_lifecycle_status" in payload:
        return "codex_task_lifecycle_summary"
    if role == "doctor_report" and "overall_doctor_status" in payload:
        return "codex_lifecycle_doctor"
    if role == "test_provenance" and ("exit_reason" in payload or "provenance_hash" in payload):
        return "run_tests_provenance"
    return None


def _status_hint(role: str, payload: Mapping[str, Any] | None) -> str | None:
    if payload is None:
        return None
    if role == "matrix" and isinstance(payload.get("status"), str):
        return str(payload["status"])
    if role in {"pre_commit_finalizer", "pr_metadata_finalizer"}:
        return _finalizer_status(payload)
    if role == "pr_metadata_guard" and isinstance(payload.get("status"), str):
        return str(payload["status"])
    if role == "lifecycle_summary" and isinstance(payload.get("overall_lifecycle_status"), str):
        return str(payload["overall_lifecycle_status"])
    if role == "doctor_report" and isinstance(payload.get("overall_doctor_status"), str):
        return str(payload["overall_doctor_status"])
    if role == "test_provenance" and isinstance(payload.get("exit_reason"), str):
        return str(payload["exit_reason"])
    return None


def _artifact(role: str, path_text: str | None) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    artifact: dict[str, Any] = {
        "role": role,
        "path": path_text,
        "exists": False,
        "readable_json": False,
        "digest": None,
        "digest_algo": DIGEST_ALGO,
        "byte_size": None,
        "status_hint": None,
        "schema_hint": None,
    }
    if not path_text:
        artifact["error"] = "path_not_provided"
        return artifact, None
    path = Path(path_text)
    if not path.exists():
        artifact["error"] = "path_missing"
        return artifact, None
    raw = path.read_bytes()
    artifact["exists"] = True
    artifact["digest"] = _sha256(raw)
    artifact["byte_size"] = len(raw)
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        artifact["error"] = f"invalid_json:{exc}"
        return artifact, None
    if not isinstance(loaded, dict):
        artifact["error"] = "json_not_object"
        return artifact, None
    artifact["readable_json"] = True
    artifact["status_hint"] = _status_hint(role, loaded)
    artifact["schema_hint"] = _schema_hint(role, loaded)
    return artifact, loaded


def build_landing_evidence_index(request: CodexLandingEvidenceIndexRequest) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    payloads: dict[str, Mapping[str, Any]] = {}
    for role, path_text in _role_paths(request).items():
        artifact, payload = _artifact(role, path_text)
        artifacts.append(artifact)
        if payload is not None:
            payloads[role] = payload
    present = [a["role"] for a in artifacts if a["exists"] and a["readable_json"]]
    missing = [a["role"] for a in artifacts if not (a["exists"] and a["readable_json"])]
    matrix = payloads.get("matrix", {})
    aggregate_hints = {
        "matrix_status": matrix.get("status") if isinstance(matrix.get("status"), str) else None,
        "required_failure_count": matrix.get("required_failure_count") if isinstance(matrix.get("required_failure_count"), int) and not isinstance(matrix.get("required_failure_count"), bool) else None,
        "doctor_status": payloads.get("doctor_report", {}).get("overall_doctor_status"),
        "lifecycle_status": payloads.get("lifecycle_summary", {}).get("overall_lifecycle_status"),
        "pre_commit_finalizer_status": _finalizer_status(payloads["pre_commit_finalizer"]) if "pre_commit_finalizer" in payloads else None,
        "pr_metadata_finalizer_status": _finalizer_status(payloads["pr_metadata_finalizer"]) if "pr_metadata_finalizer" in payloads else None,
        "pr_metadata_guard_status": payloads.get("pr_metadata_guard", {}).get("status"),
        "test_provenance_exit_reason": payloads.get("test_provenance", {}).get("exit_reason"),
    }
    id_material = {"title": request.title, "intended_commit_title": request.intended_commit_title, "artifacts": [{"role": a["role"], "path": a["path"], "digest": a["digest"]} for a in artifacts]}
    index = {
        "evidence_index_id": _stable_id("codex_landing_evidence_index", id_material),
        "title": request.title,
        "intended_commit_title": request.intended_commit_title,
        "created_at": CREATED_AT,
        "metadata_only": True,
        "developer_workflow_evidence_only": True,
        "artifact_count": len(artifacts),
        "artifact_roles_present": present,
        "artifact_roles_missing": missing,
        "artifacts": artifacts,
        "aggregate_hints": aggregate_hints,
        "non_authority_posture": dict(NON_AUTHORITY_POSTURE),
    }
    return index


def write_landing_evidence_index(index: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
