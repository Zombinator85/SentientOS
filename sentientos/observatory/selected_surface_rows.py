from __future__ import annotations

from typing import Any

from sentientos.observatory.contract_status_consumer import missing_contract_status_rows, normalize_contract_status_row


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str(value: object) -> str:
    return str(value) if isinstance(value, (str, int, float, bool)) else ""


def _truncate(value: object, *, max_chars: int = 180) -> str | None:
    text = _as_str(value).strip()
    if not text:
        return None
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _shared_row(
    *,
    row_id: str,
    status: str,
    pointer_state: str,
    summary_reason: str,
    primary_artifact_path: str,
    created_at: str | None,
    digest_sha256: str | None,
    extras: dict[str, Any],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "row_id": row_id,
        "status": status,
        "pointer_state": pointer_state,
        "summary_reason": summary_reason,
        "primary_artifact_path": primary_artifact_path,
        "created_at": created_at,
        "digest_sha256": digest_sha256,
    }
    row.update(extras)
    return row


def _fleet_rows(payload: dict[str, Any], *, pointer_state: str, artifact_path: str, created_at: str | None, digest_sha256: str | None) -> list[dict[str, Any]]:
    readiness = _as_str(payload.get("release_readiness")) or "unknown"
    reasons = _as_list(payload.get("release_readiness_reasons"))
    first_reason = _as_str(reasons[0]) if reasons else "release_readiness_reason_unavailable"
    health_state = {
        "ready": "healthy",
        "ready_with_degradation": "degraded",
        "not_ready": "blocking",
        "blocked_by_policy": "blocking",
        "indeterminate_due_to_evidence": "missing_evidence",
    }.get(readiness, "indeterminate")
    return [
        _shared_row(
            row_id="fleet_release_readiness",
            status=readiness,
            pointer_state=pointer_state,
            summary_reason=first_reason,
            primary_artifact_path=artifact_path,
            created_at=created_at,
            digest_sha256=digest_sha256,
            extras={
                "health_state": health_state,
                "readiness_meaning": readiness,
                "policy_meaning": "release_blocking" if health_state == "blocking" else "release_advisory" if health_state in {"degraded", "missing_evidence", "indeterminate"} else "release_ready",
                "degradation_count": int(payload.get("degradation_count", 0) or 0),
                "blocking_count": int(payload.get("blocking_count", 0) or 0),
                "missing_evidence_count": int(payload.get("missing_evidence_count", 0) or 0),
            },
        )
    ]


def _strict_rows(payload: dict[str, Any], *, pointer_state: str, artifact_path: str, created_at: str | None, digest_sha256: str | None) -> list[dict[str, Any]]:
    bucket = _as_str(payload.get("bucket")) or "unknown"
    readiness = _as_str(payload.get("readiness_class")) or "unknown"
    blocking = bool(payload.get("blocking"))
    degraded = bool(payload.get("degraded"))
    if blocking:
        health_state = "blocking"
        policy_meaning = "release_blocking"
    elif degraded:
        health_state = "degraded"
        policy_meaning = "release_advisory"
    else:
        health_state = "healthy"
        policy_meaning = "release_acceptable"
    return [
        _shared_row(
            row_id="strict_audit_bucket",
            status=bucket,
            pointer_state=pointer_state,
            summary_reason=_as_str(payload.get("status_hint")) or f"bucket={bucket}",
            primary_artifact_path=artifact_path,
            created_at=created_at,
            digest_sha256=digest_sha256,
            extras={
                "health_state": health_state,
                "readiness_meaning": readiness,
                "policy_meaning": policy_meaning,
                "blocking": blocking,
                "degraded": degraded,
            },
        )
    ]


def _protected_corridor_rows(payload: dict[str, Any], *, pointer_state: str, artifact_path: str, created_at: str | None, digest_sha256: str | None) -> list[dict[str, Any]]:
    global_summary = _as_dict(payload.get("global_summary"))
    status = _as_str(global_summary.get("status")) or "provisioning_required"
    repo_health = _as_str(global_summary.get("repo_health")) or "red"
    blocking_profiles = [str(item) for item in _as_list(global_summary.get("blocking_profiles"))]
    advisory_profiles = [str(item) for item in _as_list(global_summary.get("advisory_profiles"))]
    debt_profiles = [str(item) for item in _as_list(global_summary.get("debt_profiles"))]

    if bool(global_summary.get("corridor_blocking")):
        policy_meaning = "release_blocking"
        summary_reason = f"blocking_profiles={blocking_profiles}"
    elif debt_profiles:
        policy_meaning = "release_advisory"
        summary_reason = f"debt_profiles={debt_profiles}"
    elif advisory_profiles:
        policy_meaning = "release_advisory"
        summary_reason = f"advisory_profiles={advisory_profiles}"
    else:
        policy_meaning = "release_acceptable"
        summary_reason = "no_corridor_failures"

    return [
        _shared_row(
            row_id="protected_corridor_global",
            status=status,
            pointer_state=pointer_state,
            summary_reason=summary_reason,
            primary_artifact_path=artifact_path,
            created_at=created_at,
            digest_sha256=digest_sha256,
            extras={
                "health_state": repo_health,
                "policy_meaning": policy_meaning,
                "blocking_profile_count": len(blocking_profiles),
                "advisory_profile_count": len(advisory_profiles),
                "debt_profile_count": len(debt_profiles),
            },
        )
    ]


def _wan_gate_rows(payload: dict[str, Any], *, pointer_state: str, artifact_path: str, created_at: str | None, digest_sha256: str | None) -> list[dict[str, Any]]:
    outcome = _as_str(payload.get("aggregate_outcome")) or "unknown"
    health_state = {
        "pass": "healthy",
        "pass_with_degradation": "degraded",
        "warning": "degraded",
        "indeterminate": "missing_evidence",
        "blocking_failure": "blocking",
    }.get(outcome, "indeterminate")
    policy_meaning = "release_blocking" if health_state == "blocking" else "release_advisory" if health_state in {"degraded", "missing_evidence", "indeterminate"} else "release_acceptable"
    return [
        _shared_row(
            row_id="wan_release_gate",
            status=outcome,
            pointer_state=pointer_state,
            summary_reason=f"aggregate_outcome={outcome}",
            primary_artifact_path=artifact_path,
            created_at=created_at,
            digest_sha256=digest_sha256,
            extras={
                "health_state": health_state,
                "policy_meaning": policy_meaning,
                "scenario_count": int(payload.get("scenario_count", 0) or 0),
                "profile": payload.get("profile"),
                "suite": payload.get("suite"),
            },
        )
    ]


def _remote_preflight_rows(payload: dict[str, Any], *, pointer_state: str, artifact_path: str, created_at: str | None, digest_sha256: str | None) -> list[dict[str, Any]]:
    transport_failures = int(payload.get("transport_or_auth_failures", 0) or 0)
    provisioning_failures = int(payload.get("runtime_root_provisioning_failures", 0) or 0)
    command_failures = int(payload.get("command_availability_failures", 0) or 0)
    success_count = int(payload.get("preflight_success_count", 0) or 0)
    window_entries = int(payload.get("window_entries", 0) or 0)

    if transport_failures > 0 or provisioning_failures > 0:
        status = "degraded"
        health_state = "blocking"
        policy_meaning = "remote_readiness_blocking"
        summary_reason = f"transport_or_provisioning_failures={transport_failures + provisioning_failures}"
    elif command_failures > 0:
        status = "degraded"
        health_state = "degraded"
        policy_meaning = "remote_readiness_advisory"
        summary_reason = f"command_availability_failures={command_failures}"
    elif success_count == 0 and window_entries > 0:
        status = "indeterminate"
        health_state = "missing_evidence"
        policy_meaning = "remote_readiness_advisory"
        summary_reason = "no_successful_preflight_records"
    elif window_entries == 0:
        status = "missing"
        health_state = "missing_evidence"
        policy_meaning = "remote_readiness_advisory"
        summary_reason = "window_entries=0"
    else:
        status = "healthy"
        health_state = "healthy"
        policy_meaning = "remote_readiness_acceptable"
        summary_reason = f"preflight_success_count={success_count}"

    return [
        _shared_row(
            row_id="remote_preflight_window",
            status=status,
            pointer_state=pointer_state,
            summary_reason=summary_reason,
            primary_artifact_path=artifact_path,
            created_at=created_at,
            digest_sha256=digest_sha256,
            extras={
                "health_state": health_state,
                "policy_meaning": policy_meaning,
                "window_entries": window_entries,
                "preflight_success_count": success_count,
                "transport_or_auth_failures": transport_failures,
                "runtime_root_provisioning_failures": provisioning_failures,
                "command_availability_failures": command_failures,
            },
        )
    ]


def _contract_status_rows(payload: dict[str, Any], *, pointer_state: str, artifact_path: str, created_at: str | None, digest_sha256: str | None) -> list[dict[str, Any]]:
    contracts = _as_list(payload.get("contracts"))
    rows: list[dict[str, Any]] = []
    for raw in contracts:
        contract = _as_dict(raw)
        rows.append(
            normalize_contract_status_row(
                contract,
                pointer_state=pointer_state,
                primary_artifact_path=artifact_path,
                created_at=created_at,
                digest_sha256=digest_sha256,
            )
        )

    return sorted(rows, key=lambda row: str(row.get("domain") or ""))


def summary_rows_for_surface(
    *,
    surface: str,
    payload: dict[str, Any],
    pointer_state: str,
    artifact_path: str,
    created_at: str | None,
    digest_sha256: str | None,
) -> list[dict[str, Any]]:
    builders = {
        "contract_status": _contract_status_rows,
        "fleet_observatory": _fleet_rows,
        "strict_audit_status": _strict_rows,
        "protected_corridor": _protected_corridor_rows,
        "wan_gate": _wan_gate_rows,
        "remote_preflight_trend": _remote_preflight_rows,
    }
    builder = builders.get(surface)
    if builder is None:
        return []
    return builder(
        payload,
        pointer_state=pointer_state,
        artifact_path=artifact_path,
        created_at=created_at,
        digest_sha256=digest_sha256,
    )


def missing_summary_rows(*, surface: str, pointer_state: str) -> list[dict[str, Any]]:
    if surface not in {"contract_status", "fleet_observatory", "strict_audit_status", "protected_corridor", "wan_gate", "remote_preflight_trend"}:
        return []
    if surface == "contract_status":
        return missing_contract_status_rows(pointer_state=pointer_state)
    return [
        {
            "row_id": f"{surface}_missing",
            "status": "missing",
            "pointer_state": pointer_state,
            "health_state": "missing_evidence",
            "policy_meaning": "read_source_artifact",
            "summary_reason": "latest_pointer_missing",
            "primary_artifact_path": None,
            "created_at": None,
            "digest_sha256": None,
        }
    ]
