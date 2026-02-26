from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ConsistencyResult:
    status: str
    reason: str
    evidence_paths: list[str]


def compare_tick_vs_replay(latest_integrity_status: dict[str, Any], latest_replay_report: dict[str, Any]) -> ConsistencyResult:
    tick_policy_hash = _as_str(latest_integrity_status.get("policy_hash"))
    replay_policy_hash = _as_str(latest_replay_report.get("policy_hash"))
    if tick_policy_hash != replay_policy_hash:
        return ConsistencyResult(status="fail", reason="policy_hash_mismatch", evidence_paths=_evidence(latest_integrity_status, latest_replay_report))

    tick_integrity_hash = _as_str(latest_integrity_status.get("integrity_status_hash"))
    replay_integrity_hash = _as_str(latest_replay_report.get("integrity_status_hash"))
    if tick_integrity_hash != replay_integrity_hash:
        return ConsistencyResult(status="fail", reason="integrity_status_hash_mismatch", evidence_paths=_evidence(latest_integrity_status, latest_replay_report))

    tick_status = _status(latest_integrity_status)
    replay_status = _status(latest_replay_report)
    if replay_status == "fail" and tick_status in {"ok", "warn"}:
        return ConsistencyResult(status="fail", reason="replay_fail_tick_nonfail", evidence_paths=_evidence(latest_integrity_status, latest_replay_report))
    if tick_status == "fail" and replay_status == "ok":
        return ConsistencyResult(status="warn", reason="tick_fail_replay_ok", evidence_paths=_evidence(latest_integrity_status, latest_replay_report))
    return ConsistencyResult(status="ok", reason="consistent", evidence_paths=_evidence(latest_integrity_status, latest_replay_report))


def replay_is_recent(latest_replay_report: dict[str, Any], *, max_age_seconds: int = 6 * 60 * 60, now: datetime | None = None) -> bool:
    ts = _as_str(latest_replay_report.get("ts"))
    if not ts:
        return False
    parsed = _parse_iso(ts)
    if parsed is None:
        return False
    current = now or datetime.now(timezone.utc)
    return (current - parsed).total_seconds() <= max_age_seconds


def _status(payload: dict[str, Any]) -> str:
    value = _as_str(payload.get("integrity_overall")) or _as_str(payload.get("status"))
    return value or "missing"


def _evidence(tick: dict[str, Any], replay: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    tick_path = _as_str(tick.get("path"))
    replay_path = _as_str(replay.get("path"))
    if tick_path:
        paths.append(tick_path)
    if replay_path:
        paths.append(replay_path)
    return paths


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _parse_iso(value: str) -> datetime | None:
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


__all__ = ["ConsistencyResult", "compare_tick_vs_replay", "replay_is_recent"]
