from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping

from scripts.emit_baseline_verification_status import LaneSummary, _mypy_summary, _run_tests_summary
from sentientos.attestation import iso_now, write_json
from sentientos.broad_lane_rows import build_broad_lane_row, rows_from_broad_lane_summary

BroadPointerState = Literal["current", "stale", "missing", "unavailable", "incomplete"]


@dataclass(frozen=True)
class LanePointer:
    lane: str
    status: str
    lane_state: str
    pointer_state: BroadPointerState
    primary_artifact_path: str | None
    supporting_artifact_paths: list[str]
    created_at: str | None
    run_id: str | None
    digest_sha256: str | None
    provenance_resolution: dict[str, Any]
    why_latest: str
    failure_count: int
    details: dict[str, Any]

    def to_payload(self, *, generated_at: str, freshness_hours: int) -> dict[str, Any]:
        row = build_broad_lane_row(
            lane=self.lane,
            status=self.status,
            lane_state=self.lane_state,
            pointer_state=self.pointer_state,
            primary_artifact_path=self.primary_artifact_path,
            supporting_artifact_paths=self.supporting_artifact_paths,
            created_at=self.created_at,
            run_id=self.run_id,
            digest_sha256=self.digest_sha256,
            provenance_resolution=self.provenance_resolution,
            why_latest=self.why_latest,
            freshness_hours=freshness_hours,
            failure_count=self.failure_count,
            details=self.details,
        )
        return {
            "schema_version": 1,
            "generated_at": generated_at,
            "lane": row["lane"],
            "status": row["status"],
            "lane_state": row["lane_state"],
            "pointer_state": row["pointer_state"],
            "primary_artifact_path": row["primary_artifact_path"],
            "supporting_artifact_paths": row["supporting_artifact_paths"],
            "created_at": row["created_at"],
            "run_id": row["run_id"],
            "digest_sha256": row["digest_sha256"],
            "provenance_resolution": row["provenance_resolution"],
            "why_latest": row["why_latest"],
            "freshness_hours": row["freshness_hours"],
            "failure_count": row["failure_count"],
            "details": row["details"],
            "policy_meaning": row["policy_meaning"],
            "summary_reason": row["summary_reason"],
        }


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _as_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _hash_file(path: Path) -> str | None:
    try:
        import hashlib

        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _created_at_from_payload(path: Path, payload: Mapping[str, Any] | None, keys: tuple[str, ...]) -> str | None:
    if isinstance(payload, Mapping):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    try:
        fallback = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None
    return fallback.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sort_key(*, created_at: str | None, run_id: str | None, path: str) -> tuple[tuple[int, str], str, str]:
    parsed = _as_datetime(created_at)
    if parsed is None:
        created_key = (0, "")
    else:
        created_key = (int(parsed.timestamp()), created_at or "")
    return (created_key, run_id or "", path)


def _resolve_pointer_state(*, lane_state: str, created_at: str | None, now: datetime, freshness_hours: int, supporting_missing: bool = False) -> BroadPointerState:
    if lane_state == "lane_not_run":
        return "missing"
    if lane_state == "lane_unavailable_in_environment":
        return "unavailable"
    if lane_state == "lane_incomplete" or supporting_missing:
        return "incomplete"
    parsed = _as_datetime(created_at)
    if parsed is None:
        return "unavailable"
    age_hours = (now - parsed).total_seconds() / 3600.0
    return "stale" if age_hours > float(freshness_hours) else "current"


def _run_tests_lane(root: Path, now: datetime, freshness_hours: int) -> LanePointer:
    latest_path = root / "glow/test_runs/test_run_provenance.json"
    snapshot_paths = sorted(path for path in (root / "glow/test_runs/provenance").glob("*.json") if path.is_file())
    candidates = sorted({latest_path, *snapshot_paths}, key=lambda p: str(p))

    selected_path: Path | None = None
    selected_payload: dict[str, Any] | None = None
    selected_created_at: str | None = None
    selected_run_id: str | None = None
    why_latest = "no provenance artifacts found"

    evaluated: list[dict[str, Any]] = []
    for candidate in candidates:
        payload = _read_json(candidate)
        if payload is None:
            continue
        created_at = _created_at_from_payload(candidate, payload, ("timestamp", "generated_at", "created_at"))
        run_id = str(payload.get("provenance_hash") or payload.get("run_id") or "") or None
        rel = str(candidate.relative_to(root))
        evaluated.append({"path": rel, "created_at": created_at, "run_id": run_id})
        if selected_path is None or _sort_key(created_at=created_at, run_id=run_id, path=rel) > _sort_key(
            created_at=selected_created_at,
            run_id=selected_run_id,
            path=str(selected_path.relative_to(root)),
        ):
            selected_path = candidate
            selected_payload = payload
            selected_created_at = created_at
            selected_run_id = run_id

    failure_digest_path = root / "glow/test_runs/test_failure_digest.json"
    failure_digest = _read_json(failure_digest_path)
    lane = _run_tests_summary(failure_digest=failure_digest, run_provenance=selected_payload)

    supporting_paths: list[str] = []
    if failure_digest_path.exists():
        supporting_paths.append(str(failure_digest_path.relative_to(root)))

    supporting_missing = False
    if lane.lane_state.startswith("lane_completed") and lane.status in {"amber", "red"} and not failure_digest_path.exists():
        supporting_missing = True
        lane = LaneSummary("amber", "lane_incomplete", lane.failure_count, {**lane.details, "reason": "supporting_artifacts_missing"})

    if selected_path is not None:
        why_latest = "selected by ordering(created_at, run_id, artifact_path) across latest+snapshot provenance artifacts"

    pointer_state = _resolve_pointer_state(
        lane_state=lane.lane_state,
        created_at=selected_created_at,
        now=now,
        freshness_hours=freshness_hours,
        supporting_missing=supporting_missing,
    )

    return LanePointer(
        lane="run_tests",
        status=lane.status,
        lane_state=lane.lane_state,
        pointer_state=pointer_state,
        primary_artifact_path=(str(selected_path.relative_to(root)) if selected_path is not None else None),
        supporting_artifact_paths=supporting_paths,
        created_at=selected_created_at,
        run_id=selected_run_id,
        digest_sha256=_hash_file(selected_path) if selected_path is not None else None,
        provenance_resolution={
            "mode": "glob+single",
            "paths": ["glow/test_runs/test_run_provenance.json", "glow/test_runs/provenance/*.json"],
            "ordering": ["created_at", "run_id", "artifact_path"],
            "evaluated_candidates": evaluated,
        },
        why_latest=why_latest,
        failure_count=lane.failure_count,
        details=lane.details,
    )


def _mypy_lane(root: Path, now: datetime, freshness_hours: int) -> LanePointer:
    candidates = [
        root / "glow/contracts/typing_ratchet_status.json",
        root / "glow/forge/ratchets/mypy_ratchet_status.json",
    ]
    text_summary_path = root / "glow/typecheck/mypy_latest.txt"
    if text_summary_path.exists() and text_summary_path.is_file():
        candidates.append(text_summary_path)

    selected_path: Path | None = None
    selected_payload: dict[str, Any] | None = None
    selected_created_at: str | None = None
    selected_run_id: str | None = None
    evaluated: list[dict[str, Any]] = []

    for candidate in candidates:
        if not candidate.exists() or not candidate.is_file():
            continue
        payload = _read_json(candidate) if candidate.suffix == ".json" else None
        created_at = _created_at_from_payload(candidate, payload, ("generated_at", "timestamp", "created_at"))
        run_id = None
        if isinstance(payload, Mapping):
            run_id = str(payload.get("run_id") or payload.get("provenance_hash") or "") or None
        rel = str(candidate.relative_to(root))
        evaluated.append({"path": rel, "created_at": created_at, "run_id": run_id})
        if selected_path is None or _sort_key(created_at=created_at, run_id=run_id, path=rel) > _sort_key(
            created_at=selected_created_at,
            run_id=selected_run_id,
            path=str(selected_path.relative_to(root)),
        ):
            selected_path = candidate
            selected_payload = payload
            selected_created_at = created_at
            selected_run_id = run_id

    lane = _mypy_summary(output_path=text_summary_path, ratchet_status=selected_payload)

    supporting_paths: list[str] = []
    for support in (
        root / "glow/contracts/typing_ratchet_status.json",
        root / "glow/forge/ratchets/mypy_ratchet_status.json",
        text_summary_path,
    ):
        if support.exists() and support.is_file() and support != selected_path:
            supporting_paths.append(str(support.relative_to(root)))

    why_latest = "no mypy artifacts found"
    if selected_path is not None:
        why_latest = "selected by ordering(created_at, run_id, artifact_path) across ratchet and legacy mypy artifacts"

    pointer_state = _resolve_pointer_state(
        lane_state=lane.lane_state,
        created_at=selected_created_at,
        now=now,
        freshness_hours=freshness_hours,
    )

    return LanePointer(
        lane="mypy",
        status=lane.status,
        lane_state=lane.lane_state,
        pointer_state=pointer_state,
        primary_artifact_path=(str(selected_path.relative_to(root)) if selected_path is not None else None),
        supporting_artifact_paths=supporting_paths,
        created_at=selected_created_at,
        run_id=selected_run_id,
        digest_sha256=_hash_file(selected_path) if selected_path is not None else None,
        provenance_resolution={
            "mode": "explicit",
            "paths": [
                "glow/contracts/typing_ratchet_status.json",
                "glow/forge/ratchets/mypy_ratchet_status.json",
                "glow/typecheck/mypy_latest.txt",
            ],
            "ordering": ["created_at", "run_id", "artifact_path"],
            "evaluated_candidates": evaluated,
        },
        why_latest=why_latest,
        failure_count=lane.failure_count,
        details=lane.details,
    )


def _combined_pointer_state(pointers: list[LanePointer]) -> BroadPointerState:
    states = {pointer.pointer_state for pointer in pointers}
    for state in ("missing", "unavailable", "incomplete", "stale"):
        if state in states:
            return state
    return "current"


def emit_broad_lane_latest_pointers(repo_root: Path, *, freshness_hours: int = 24) -> dict[str, Any]:
    root = repo_root.resolve()
    out_dir = root / "glow/observatory/broad_lane"
    out_dir.mkdir(parents=True, exist_ok=True)

    generated_at = iso_now()
    now = _as_datetime(generated_at) or datetime.now(timezone.utc)

    run_tests_pointer = _run_tests_lane(root, now, freshness_hours)
    mypy_pointer = _mypy_lane(root, now, freshness_hours)

    lane_payloads = {
        "run_tests": run_tests_pointer.to_payload(generated_at=generated_at, freshness_hours=freshness_hours),
        "mypy": mypy_pointer.to_payload(generated_at=generated_at, freshness_hours=freshness_hours),
    }

    combined = {
        "schema_version": 1,
        "generated_at": generated_at,
        "surface": "broad_lane_latest_summary",
        "pointer_state": _combined_pointer_state([run_tests_pointer, mypy_pointer]),
        "broad_baseline_green": run_tests_pointer.status == "green" and mypy_pointer.status == "green",
        "lanes": lane_payloads,
        "artifact_paths": {
            "run_tests": "glow/observatory/broad_lane/run_tests_latest_pointer.json",
            "mypy": "glow/observatory/broad_lane/mypy_latest_pointer.json",
        },
    }
    combined["lane_rows"] = rows_from_broad_lane_summary(combined)

    write_json(out_dir / "run_tests_latest_pointer.json", lane_payloads["run_tests"])
    write_json(out_dir / "mypy_latest_pointer.json", lane_payloads["mypy"])
    write_json(out_dir / "broad_lane_latest_summary.json", combined)

    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "status": "passed",
        "ok": True,
        "artifact_paths": {
            "run_tests_latest_pointer": "glow/observatory/broad_lane/run_tests_latest_pointer.json",
            "mypy_latest_pointer": "glow/observatory/broad_lane/mypy_latest_pointer.json",
            "broad_lane_latest_summary": "glow/observatory/broad_lane/broad_lane_latest_summary.json",
        },
        "surface_states": {
            "run_tests": run_tests_pointer.pointer_state,
            "mypy": mypy_pointer.pointer_state,
            "broad_lane": combined["pointer_state"],
        },
    }
