from __future__ import annotations

from typing import Any, Literal, Mapping

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
        return pointer_state
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
        "created_at": created_at if isinstance(created_at, str) and created_at else None,
        "run_id": run_id if isinstance(run_id, str) and run_id else None,
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
    lanes = payload.get("lanes")
    if not isinstance(lanes, Mapping):
        return []
    rows: list[dict[str, Any]] = []
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
        rows.append(
            build_broad_lane_row(
                lane=lane_name,
                status=status,
                lane_state=lane_state,
                pointer_state=lane_payload.get("pointer_state"),
                primary_artifact_path=lane_payload.get("primary_artifact_path"),
                created_at=lane_payload.get("created_at"),
                run_id=lane_payload.get("run_id"),
                failure_count=lane_payload.get("failure_count"),
                details=lane_payload.get("details"),
            )
        )
    return rows
