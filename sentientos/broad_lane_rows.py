from __future__ import annotations

from typing import Any, Literal, Mapping, cast

BroadLanePointerState = Literal["current", "stale", "missing", "unavailable", "incomplete"]
BroadLanePolicyMeaning = Literal["corridor_blocking", "broad_lane_only", "advisory", "deferred"]

_POINTER_STATES: tuple[str, ...] = ("current", "stale", "missing", "unavailable", "incomplete")


def policy_meaning_for_lane_state(*, lane: str, lane_state: str) -> BroadLanePolicyMeaning:
    if lane_state == "lane_completed_with_blocking_failure":
        return "corridor_blocking" if lane == "protected_corridor" else "broad_lane_only"
    if lane_state == "lane_completed_with_deferred_debt":
        return "deferred"
    return "advisory"


def _normalize_pointer_state(pointer_state: object, *, lane_state: str) -> BroadLanePointerState:
    if isinstance(pointer_state, str) and pointer_state in _POINTER_STATES:
        return cast(BroadLanePointerState, pointer_state)
    if lane_state == "lane_not_run":
        return "missing"
    if lane_state == "lane_unavailable_in_environment":
        return "unavailable"
    if lane_state == "lane_incomplete":
        return "incomplete"
    return "unavailable"


def summary_reason(*, pointer_state: str, lane_state: str, policy_meaning: str) -> str:
    return f"pointer={pointer_state}; lane={lane_state}; policy={policy_meaning}"


def build_broad_lane_row(
    *,
    lane: str,
    status: str,
    lane_state: str,
    pointer_state: object,
    primary_artifact_path: object = None,
    created_at: object = None,
    run_id: object = None,
    supporting_artifact_paths: object = None,
    digest_sha256: object = None,
    provenance_resolution: object = None,
    why_latest: object = None,
    freshness_hours: object = None,
    failure_count: object = None,
    details: object = None,
) -> dict[str, Any]:
    normalized_pointer_state = _normalize_pointer_state(pointer_state, lane_state=lane_state)
    policy_meaning = policy_meaning_for_lane_state(lane=lane, lane_state=lane_state)
    return {
        "lane": lane,
        "status": status,
        "lane_state": lane_state,
        "pointer_state": normalized_pointer_state,
        "primary_artifact_path": primary_artifact_path if isinstance(primary_artifact_path, str) and primary_artifact_path else None,
        "supporting_artifact_paths": [str(path) for path in supporting_artifact_paths if isinstance(path, str) and path]
        if isinstance(supporting_artifact_paths, list)
        else [],
        "created_at": created_at if isinstance(created_at, str) and created_at else None,
        "run_id": run_id if isinstance(run_id, str) and run_id else None,
        "digest_sha256": digest_sha256 if isinstance(digest_sha256, str) and digest_sha256 else None,
        "provenance_resolution": dict(provenance_resolution) if isinstance(provenance_resolution, Mapping) else {},
        "why_latest": why_latest if isinstance(why_latest, str) and why_latest else None,
        "freshness_hours": freshness_hours if isinstance(freshness_hours, int) else None,
        "failure_count": failure_count if isinstance(failure_count, int) else 0,
        "details": dict(details) if isinstance(details, Mapping) else {},
        "policy_meaning": policy_meaning,
        "summary_reason": summary_reason(
            pointer_state=normalized_pointer_state,
            lane_state=lane_state,
            policy_meaning=policy_meaning,
        ),
    }


def rows_from_broad_lane_summary(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    explicit_rows = payload.get("lane_rows")
    if isinstance(explicit_rows, list):
        rows: list[dict[str, Any]] = []
        for row in explicit_rows:
            if not isinstance(row, Mapping):
                continue
            lane = row.get("lane")
            status = row.get("status")
            lane_state = row.get("lane_state")
            if not isinstance(lane, str) or not lane:
                continue
            if not isinstance(status, str) or not status:
                continue
            if not isinstance(lane_state, str) or not lane_state:
                continue
            rows.append(
                build_broad_lane_row(
                    lane=lane,
                    status=status,
                    lane_state=lane_state,
                    pointer_state=row.get("pointer_state"),
                    primary_artifact_path=row.get("primary_artifact_path"),
                    supporting_artifact_paths=row.get("supporting_artifact_paths"),
                    created_at=row.get("created_at"),
                    run_id=row.get("run_id"),
                    digest_sha256=row.get("digest_sha256"),
                    provenance_resolution=row.get("provenance_resolution"),
                    why_latest=row.get("why_latest"),
                    freshness_hours=row.get("freshness_hours"),
                    failure_count=row.get("failure_count"),
                    details=row.get("details"),
                )
            )
        if rows:
            return rows
    lanes = payload.get("lanes")
    if not isinstance(lanes, Mapping):
        return []
    mapped_rows: list[dict[str, Any]] = []
    for lane_name in ("run_tests", "mypy"):
        lane_payload = lanes.get(lane_name)
        if not isinstance(lane_payload, Mapping):
            continue
        status = lane_payload.get("status")
        lane_state = lane_payload.get("lane_state")
        if not isinstance(status, str) or not status:
            continue
        if not isinstance(lane_state, str) or not lane_state:
            continue
        mapped_rows.append(
            build_broad_lane_row(
                lane=lane_name,
                status=status,
                lane_state=lane_state,
                pointer_state=lane_payload.get("pointer_state"),
                primary_artifact_path=lane_payload.get("primary_artifact_path"),
                supporting_artifact_paths=lane_payload.get("supporting_artifact_paths"),
                created_at=lane_payload.get("created_at"),
                run_id=lane_payload.get("run_id"),
                digest_sha256=lane_payload.get("digest_sha256"),
                provenance_resolution=lane_payload.get("provenance_resolution"),
                why_latest=lane_payload.get("why_latest"),
                freshness_hours=lane_payload.get("freshness_hours"),
                failure_count=lane_payload.get("failure_count"),
                details=lane_payload.get("details"),
            )
        )
    return mapped_rows
