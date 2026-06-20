from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from sentientos.codex_landing_evidence_index import ARTIFACT_ROLES

READY = "doctor_ready"
BLOCKED = "doctor_blocked"
INCOMPLETE = "doctor_incomplete"
STALE = "doctor_stale"
RERUN_REQUIRED = "doctor_rerun_required"

NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "doctor_is_read_only": True,
    "doctor_does_not_rerun_commands": True,
    "doctor_does_not_bypass_finalizer": True,
    "doctor_does_not_bypass_pr_metadata_guard": True,
    "doctor_does_not_authorize_commit": True,
    "doctor_does_not_authorize_pr_creation": True,
    "doctor_does_not_authorize_runtime_action": True,
    "doctor_uses_index_only_as_manifest": True,
    "doctor_reads_underlying_artifacts": True,
    "doctor_does_not_trust_index_hints_as_authority": True,
}

INDEX_CONSUMED_ROLES: tuple[str, ...] = tuple(
    role
    for role in ARTIFACT_ROLES
    if role in {
        "matrix",
        "pre_commit_finalizer",
        "pr_metadata_finalizer",
        "pr_metadata_guard",
        "lifecycle_summary",
        "test_provenance",
    }
)

ROLE_TO_REQUEST_FIELD: dict[str, str] = {
    "matrix": "matrix_json_path",
    "pre_commit_finalizer": "pre_commit_finalizer_json",
    "pr_metadata_finalizer": "pr_metadata_finalizer_json",
    "pr_metadata_guard": "pr_metadata_guard_json",
    "lifecycle_summary": "lifecycle_summary_json",
    "test_provenance": "test_provenance_json",
}


class CodexLifecycleDoctorError(ValueError):
    """Raised when doctor evidence cannot be read as deterministic JSON."""


@dataclass(frozen=True)
class CodexLifecycleDoctorRequest:
    title: str
    intended_commit_title: str
    matrix_json_path: str | None = None
    pre_commit_finalizer_json: str | None = None
    pr_metadata_finalizer_json: str | None = None
    pr_metadata_guard_json: str | None = None
    lifecycle_summary_json: str | None = None
    test_provenance_json: str | None = None
    evidence_index_json: str | None = None
    output: str | None = None


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\u241f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _load_json_object(path_text: str, label: str, missing: list[str]) -> dict[str, Any] | None:
    path = Path(path_text)
    if not path.exists():
        missing.append(label)
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CodexLifecycleDoctorError(f"{label}_invalid_json:{path_text}:{exc.msg}") from exc
    if not isinstance(loaded, dict):
        raise CodexLifecycleDoctorError(f"{label}_json_not_object:{path_text}")
    return loaded



def _load_evidence_index(path_text: str, missing: list[str]) -> dict[str, Any] | None:
    return _load_json_object(path_text, "evidence_index_json", missing)


def _index_artifact_paths(index: Mapping[str, Any] | None) -> dict[str, str]:
    if index is None:
        return {}
    artifacts = index.get("artifacts")
    if not isinstance(artifacts, list):
        return {}
    paths: dict[str, str] = {}
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            continue
        role = artifact.get("role")
        path = artifact.get("path")
        if isinstance(role, str) and role in INDEX_CONSUMED_ROLES and isinstance(path, str) and path:
            paths[role] = path
    return paths


def _resolve_request_paths(request: CodexLifecycleDoctorRequest, index: Mapping[str, Any] | None) -> tuple[dict[str, str | None], dict[str, Any] | None]:
    index_paths = _index_artifact_paths(index)
    resolved = {field: getattr(request, field) for field in ROLE_TO_REQUEST_FIELD.values()}
    used: list[str] = []
    overridden: list[str] = []
    unusable: list[dict[str, str]] = []
    for role in INDEX_CONSUMED_ROLES:
        field = ROLE_TO_REQUEST_FIELD[role]
        explicit = getattr(request, field)
        index_path = index_paths.get(role)
        if explicit:
            if index_path:
                overridden.append(role)
            continue
        if not index_path:
            continue
        if Path(index_path).exists():
            resolved[field] = index_path
            used.append(role)
        else:
            unusable.append({"role": role, "path": index_path, "reason": "path_missing"})
            if role == "matrix":
                resolved[field] = index_path
                used.append(role)
    if index is None:
        return resolved, None
    present_raw = index.get("artifact_roles_present")
    missing_raw = index.get("artifact_roles_missing")
    present = [str(role) for role in present_raw] if isinstance(present_raw, list) else sorted(index_paths)
    missing = [str(role) for role in missing_raw] if isinstance(missing_raw, list) else [role for role in INDEX_CONSUMED_ROLES if role not in present]
    nonauth = index.get("non_authority_posture")
    summary = {
        "path": request.evidence_index_json,
        "readable_json": True,
        "evidence_index_id": index.get("evidence_index_id") if isinstance(index.get("evidence_index_id"), str) else None,
        "roles_present": sorted(present),
        "roles_missing": sorted(missing),
        "used_roles": sorted(used),
        "overridden_roles": sorted(overridden),
        "unusable_roles": sorted(unusable, key=lambda item: (item["role"], item["path"])),
        "non_authority_posture_seen": bool(nonauth) if isinstance(nonauth, Mapping) else False,
    }
    return resolved, summary

def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _finalizer_status(payload: Mapping[str, Any] | None) -> str | None:
    if payload is None:
        return None
    decision = payload.get("decision")
    if isinstance(decision, Mapping) and isinstance(decision.get("status"), str):
        return str(decision["status"])
    if isinstance(payload.get("status"), str):
        return str(payload["status"])
    return None


def _freshness(payload: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if payload is None:
        return {}
    freshness = payload.get("evidence_freshness")
    return freshness if isinstance(freshness, Mapping) else {}


def _is_stale_refresh(value: Any) -> bool:
    return isinstance(value, str) and value not in {"", "not_required", "succeeded", "ready", "passed", "not_applicable"}


def _matrix_summary(matrix: Mapping[str, Any]) -> dict[str, Any]:
    results = matrix.get("results")
    rows = results if isinstance(results, list) else []
    blocked: list[dict[str, Any]] = []
    proof_required_count = 0
    proof_passed_count = 0
    diagnostic_failure_count = _as_int(matrix.get("diagnostic_failure_count")) or 0
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        proof_required = bool(row.get("proof_required", row.get("required", False)))
        required = bool(row.get("required", False))
        proof_status = str(row.get("proof_status", ""))
        diagnostic_only = bool(row.get("diagnostic_only", False))
        if proof_required:
            proof_required_count += 1
        if proof_status == "proof-passed":
            proof_passed_count += 1
        if diagnostic_only and proof_status.startswith("nonproof-diagnostic-failed"):
            diagnostic_failure_count += 1
        if required and proof_status != "proof-passed":
            blocked.append(
                {
                    "lane": str(row.get("label") or row.get("id") or "unknown"),
                    "proof_status": proof_status or None,
                    "exit_reason": row.get("exit_reason"),
                    "classification": row.get("classification_reason") or ("required_proof_failure" if proof_required else "required_nonproof_failure"),
                }
            )
    return {
        "status": matrix.get("status"),
        "required_failure_count": _as_int(matrix.get("required_failure_count")),
        "nonproof_count": _as_int(matrix.get("nonproof_count")),
        "diagnostic_failure_count": diagnostic_failure_count,
        "proof_required_count": _as_int(matrix.get("proof_required_count")) if matrix.get("proof_required_count") is not None else proof_required_count,
        "proof_passed_count": _as_int(matrix.get("proof_passed_count")) if matrix.get("proof_passed_count") is not None else proof_passed_count,
        "blocked_lane_count": len(blocked),
        "blocked_lanes": blocked,
    }


def _finalizer_summary(pre: Mapping[str, Any] | None, pr: Mapping[str, Any] | None) -> dict[str, Any]:
    pre_fresh = _freshness(pre)
    pr_fresh = _freshness(pr)
    return {
        "pre_commit_status": _finalizer_status(pre),
        "pr_metadata_status": _finalizer_status(pr),
        "terminal_refresh_status": {"pre_commit": pre_fresh.get("terminal_refresh_status"), "pr_metadata": pr_fresh.get("terminal_refresh_status")},
        "rerun_required": {"pre_commit": pre_fresh.get("rerun_required"), "pr_metadata": pr_fresh.get("rerun_required")},
        "stale_evidence_refresh_result": {"pre_commit": pre_fresh.get("stale_evidence_refresh_result"), "pr_metadata": pr_fresh.get("stale_evidence_refresh_result")},
        "cleaned_paths_count": len(pre_fresh.get("cleaned_paths") or []) + len(pr_fresh.get("cleaned_paths") or []),
        "terminal_cleaned_paths_count": len(pre_fresh.get("terminal_cleaned_paths") or []) + len(pr_fresh.get("terminal_cleaned_paths") or []),
    }


def _guard_summary(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {"status": None, "ready": None}
    status = payload.get("status")
    return {"status": status, "ready": status == "pr_metadata_guard_ready" or payload.get("ready") is True}


def _lifecycle_summary(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {"overall_lifecycle_status": None, "rerun_required": None, "rerun_reason": None}
    return {"overall_lifecycle_status": payload.get("overall_lifecycle_status"), "rerun_required": payload.get("rerun_required"), "rerun_reason": payload.get("rerun_reason")}


def _test_provenance_summary(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {"run_intent": None, "execution_mode": None, "tests_selected": None, "tests_executed": None, "tests_passed": None, "tests_skipped": None, "exit_reason": None, "proof_quality": None}
    selected = _as_int(payload.get("tests_selected"))
    executed = _as_int(payload.get("tests_executed"))
    passed = _as_int(payload.get("tests_passed"))
    run_intent = payload.get("run_intent")
    proof_quality = True
    if run_intent in {"targeted", "focused"}:
        proof_quality = bool(selected and selected > 0 and executed and executed > 0 and passed and passed > 0)
    return {
        "run_intent": run_intent,
        "execution_mode": payload.get("execution_mode"),
        "tests_selected": selected,
        "tests_executed": executed,
        "tests_passed": passed,
        "tests_skipped": _as_int(payload.get("tests_skipped")),
        "exit_reason": payload.get("exit_reason"),
        "proof_quality": proof_quality,
    }


def build_lifecycle_doctor_report(request: CodexLifecycleDoctorRequest) -> dict[str, Any]:
    missing: list[str] = []
    evidence_index = _load_evidence_index(request.evidence_index_json, missing) if request.evidence_index_json else None
    resolved_paths, evidence_index_summary = _resolve_request_paths(request, evidence_index)
    matrix_path = resolved_paths["matrix_json_path"]
    if matrix_path:
        matrix = _load_json_object(matrix_path, "matrix_json_path", missing) or {}
    else:
        missing.append("matrix_json_path")
        matrix = {}
    pre_path = resolved_paths["pre_commit_finalizer_json"]
    pr_path = resolved_paths["pr_metadata_finalizer_json"]
    guard_path = resolved_paths["pr_metadata_guard_json"]
    lifecycle_path = resolved_paths["lifecycle_summary_json"]
    provenance_path = resolved_paths["test_provenance_json"]
    pre = _load_json_object(pre_path, "pre_commit_finalizer_json", missing) if pre_path else None
    pr = _load_json_object(pr_path, "pr_metadata_finalizer_json", missing) if pr_path else None
    guard = _load_json_object(guard_path, "pr_metadata_guard_json", missing) if guard_path else None
    lifecycle = _load_json_object(lifecycle_path, "lifecycle_summary_json", missing) if lifecycle_path else None
    provenance = _load_json_object(provenance_path, "test_provenance_json", missing) if provenance_path else None

    matrix_s = _matrix_summary(matrix)
    finalizer_s = _finalizer_summary(pre, pr)
    guard_s = _guard_summary(guard)
    lifecycle_s = _lifecycle_summary(lifecycle)
    provenance_s = _test_provenance_summary(provenance)

    reasons: list[str] = []
    status = READY
    action = "no_action_ready"
    if missing:
        status, action = INCOMPLETE, "provide_missing_evidence"
        reasons.append("missing_evidence:" + ",".join(sorted(missing)))
    elif (matrix_s["required_failure_count"] or 0) > 0 or matrix_s["blocked_lane_count"] > 0:
        status, action = BLOCKED, "inspect_blocked_lanes"
        reasons.append("matrix_required_proof_blocked")
    elif pre is not None and finalizer_s["pre_commit_status"] != "ready_to_commit":
        status, action = BLOCKED, "rerun_finalizer_with_refresh"
        reasons.append(f"pre_commit_finalizer_not_ready:{finalizer_s['pre_commit_status']}")
    elif pr is not None and finalizer_s["pr_metadata_status"] != "ready_for_pr_metadata":
        status, action = BLOCKED, "rerun_finalizer_with_refresh"
        reasons.append(f"pr_metadata_finalizer_not_ready:{finalizer_s['pr_metadata_status']}")
    elif guard is not None and guard_s["status"] != "pr_metadata_guard_ready":
        status, action = BLOCKED, "provide_missing_evidence"
        reasons.append(f"pr_metadata_guard_not_ready:{guard_s['status']}")
    elif lifecycle is not None and lifecycle_s["overall_lifecycle_status"] != "codex_lifecycle_ready":
        status, action = RERUN_REQUIRED if lifecycle_s["rerun_required"] is True else BLOCKED, "rerun_matrix"
        reasons.append(f"lifecycle_not_ready:{lifecycle_s['overall_lifecycle_status']}")
    elif provenance is not None and provenance_s["proof_quality"] is False:
        status, action = BLOCKED, "inspect_test_airlock_provenance"
        reasons.append("targeted_test_provenance_not_proof_quality")

    stale_values = [*finalizer_s["terminal_refresh_status"].values(), *finalizer_s["stale_evidence_refresh_result"].values()]
    rerun_values = [*finalizer_s["rerun_required"].values(), lifecycle_s["rerun_required"]]
    if status == READY and any(value is True for value in rerun_values):
        status, action = RERUN_REQUIRED, "rerun_finalizer_with_refresh"
        reasons.append("evidence_rerun_required")
    if status in {READY, RERUN_REQUIRED} and any(_is_stale_refresh(value) for value in stale_values):
        status, action = STALE, "rerun_finalizer_with_refresh"
        reasons.append("stale_or_refresh_required_finalizer_evidence")

    report = {
        "doctor_report_id": _stable_id("codex_lifecycle_doctor", request.title, request.intended_commit_title, str(matrix_path or "")),
        "title": request.title,
        "intended_commit_title": request.intended_commit_title,
        "overall_doctor_status": status,
        "readiness_summary": ";".join(reasons) if reasons else "available evidence is mutually ready; inspection-only, not authority",
        "missing_evidence": sorted(missing),
        "evidence_inputs": {
            "matrix_json_path": matrix_path,
            "pre_commit_finalizer_json_path": pre_path,
            "pr_metadata_finalizer_json_path": pr_path,
            "pr_metadata_guard_json_path": guard_path,
            "lifecycle_summary_json_path": lifecycle_path,
            "test_provenance_json_path": provenance_path,
            "evidence_index_json_path": request.evidence_index_json,
        },
        "matrix_summary": matrix_s,
        "finalizer_summary": finalizer_s,
        "pr_metadata_guard_summary": guard_s,
        "lifecycle_summary": lifecycle_s,
        "test_provenance_summary": provenance_s,
        "next_safe_action": action,
        "next_safe_action_reason": ";".join(reasons) if reasons else "no blocking, stale, rerun-required, or missing evidence was visible to the doctor",
        "non_authority_posture": dict(NON_AUTHORITY_POSTURE),
    }
    if evidence_index_summary is not None:
        report["evidence_index_summary"] = evidence_index_summary
        report["evidence_index_json_path"] = evidence_index_summary["path"]
        report["evidence_index_id"] = evidence_index_summary["evidence_index_id"]
        report["evidence_index_artifact_roles_present"] = evidence_index_summary["roles_present"]
        report["evidence_index_artifact_roles_missing"] = evidence_index_summary["roles_missing"]
        report["evidence_index_used_roles"] = evidence_index_summary["used_roles"]
        report["evidence_index_overridden_roles"] = evidence_index_summary["overridden_roles"]
        report["evidence_index_unusable_roles"] = evidence_index_summary["unusable_roles"]
    return report


def write_lifecycle_doctor_report(report: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
