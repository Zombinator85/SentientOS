from __future__ import annotations

from typing import Any


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: object) -> str:
    return str(value) if isinstance(value, (str, int, float, bool)) else ""


def _truncate(value: object, *, max_chars: int = 220) -> str | None:
    text = _as_str(value).strip()
    if not text:
        return None
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def normalize_contract_status_row(
    contract: dict[str, Any],
    *,
    pointer_state: str,
    primary_artifact_path: str,
    created_at: str | None,
    digest_sha256: str | None,
) -> dict[str, Any]:
    domain = _as_str(contract.get("domain_name")).strip() or "unknown_domain"
    baseline_present = bool(contract.get("baseline_present"))
    drifted_raw = contract.get("drifted")
    drifted: bool | None = drifted_raw if isinstance(drifted_raw, bool) else None
    drift_type = _as_str(contract.get("drift_type")).strip() or "unknown"
    drift_explanation = _truncate(contract.get("drift_explanation"), max_chars=220)
    strict_gate_envvar = _as_str(contract.get("strict_gate_envvar")).strip() or None

    if drift_type in {"baseline_missing", "artifact_missing", "preflight_required"} or (not baseline_present and drifted is None):
        status = "baseline_missing"
        policy_meaning = "strict_gate_precondition" if strict_gate_envvar else "missing_evidence"
        gate_meaning = "strict_gate_precondition" if strict_gate_envvar else "no_strict_gate"
    elif drifted is True:
        status = "drifted"
        policy_meaning = "strict_gate_configurable" if strict_gate_envvar else "domain_policy_defined"
        gate_meaning = "strict_gate_configurable" if strict_gate_envvar else "no_strict_gate"
    elif drifted is False:
        status = "healthy"
        policy_meaning = "contract_nominal"
        gate_meaning = "strict_gate_available" if strict_gate_envvar else "no_strict_gate"
    else:
        status = "indeterminate"
        policy_meaning = "read_source_artifact"
        gate_meaning = "indeterminate"

    if pointer_state == "current":
        freshness_posture = "fresh_evidence"
    elif pointer_state in {"missing", "unavailable"}:
        freshness_posture = "evidence_unavailable"
    else:
        freshness_posture = "stale_evidence"

    if status == "baseline_missing":
        alert_kind = "baseline_absent"
        alert_reason = "baseline_missing_for_contract_domain"
    elif status == "drifted":
        alert_kind = "domain_drift"
        alert_reason = "contract_drift_detected"
    elif status == "indeterminate":
        alert_kind = "partial_evidence"
        alert_reason = "contract_domain_indeterminate"
    elif freshness_posture != "fresh_evidence":
        alert_kind = "freshness_issue"
        alert_reason = "contract_pointer_not_current"
    else:
        alert_kind = "informational"
        alert_reason = "contract_domain_nominal"

    summary_reason = drift_explanation or f"drift_type={drift_type}; alert={alert_reason}"

    provenance = _as_dict(contract.get("drift_provenance"))
    drift_provenance_hint = _truncate(provenance.get("captured_at") or provenance.get("tool") or provenance.get("source"))

    return {
        "row_id": f"contract_domain:{domain}",
        "status": status,
        "drift_posture": status,
        "pointer_state": pointer_state,
        "freshness_posture": freshness_posture,
        "alert_kind": alert_kind,
        "alert_reason": alert_reason,
        "summary_reason": summary_reason,
        "primary_artifact_path": primary_artifact_path,
        "created_at": created_at,
        "digest_sha256": digest_sha256,
        "domain": domain,
        "policy_meaning": policy_meaning,
        "gate_meaning": gate_meaning,
        "baseline_present": baseline_present,
        "drifted": drifted,
        "drift_type": drift_type,
        "drift_explanation": drift_explanation,
        "strict_gate_envvar": strict_gate_envvar,
        "domain_artifact_path": contract.get("last_baseline_path") if isinstance(contract.get("last_baseline_path"), str) else None,
        "drift_report_path": contract.get("drift_report_path") if isinstance(contract.get("drift_report_path"), str) else None,
        "domain_captured_at": contract.get("captured_at") if isinstance(contract.get("captured_at"), str) else None,
        "domain_captured_by": contract.get("captured_by") if isinstance(contract.get("captured_by"), str) else None,
        "domain_tool_version": contract.get("tool_version") if isinstance(contract.get("tool_version"), str) else None,
        "domain_git_sha": contract.get("git_sha") if isinstance(contract.get("git_sha"), str) else None,
        "drift_provenance_hint": drift_provenance_hint,
    }


def missing_contract_status_rows(*, pointer_state: str) -> list[dict[str, Any]]:
    row = {
        "row_id": "contract_status_missing",
        "status": "missing",
        "drift_posture": "indeterminate",
        "pointer_state": pointer_state,
        "freshness_posture": "evidence_unavailable",
        "alert_kind": "freshness_issue",
        "alert_reason": "latest_pointer_missing",
        "health_state": "missing_evidence",
        "policy_meaning": "read_source_artifact",
        "gate_meaning": "indeterminate",
        "summary_reason": "latest_pointer_missing",
        "primary_artifact_path": None,
        "created_at": None,
        "digest_sha256": None,
    }
    return [row]


def summarize_contract_alerts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "freshness_issue": 0,
        "domain_drift": 0,
        "baseline_absent": 0,
        "partial_evidence": 0,
        "informational": 0,
    }
    for row in rows:
        kind = str(row.get("alert_kind") or "")
        if kind in counts:
            counts[kind] += 1

    return {
        "row_count": len(rows),
        "alert_counts": counts,
        "stale_or_missing_rows": sum(1 for row in rows if str(row.get("freshness_posture") or "") != "fresh_evidence"),
        "drifted_rows": sum(1 for row in rows if str(row.get("status") or "") == "drifted"),
        "baseline_missing_rows": sum(1 for row in rows if str(row.get("status") or "") == "baseline_missing"),
        "indeterminate_rows": sum(1 for row in rows if str(row.get("status") or "") == "indeterminate"),
    }
