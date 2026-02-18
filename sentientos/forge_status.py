"""Live forge daemon status model for observability surfaces."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any

from sentientos.contract_sentinel import ContractSentinel
from sentientos.forge_queue import ForgeQueue


@dataclass(slots=True)
class ForgeStatus:
    daemon_enabled: bool
    lock_active: bool
    lock_owner_pid: int | None
    lock_age_seconds: int | None
    lock_ttl_seconds: int
    current_request_id: str | None
    current_goal: str | None
    started_at: str | None
    runs_remaining_day: int
    runs_remaining_hour: int
    files_remaining_day: int
    last_receipt: dict[str, Any] | None
    sentinel_enabled: bool
    sentinel_last_enqueued: dict[str, Any] | None
    sentinel_state: dict[str, Any]
    last_trigger_domain: str | None
    last_quarantine: dict[str, Any] | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def compute_status(repo_root: Path) -> ForgeStatus:
    root = repo_root.resolve()
    daemon_enabled = os.getenv("SENTIENTOS_FORGE_DAEMON_ENABLED", "0") == "1"
    lock_ttl = max(60, int(os.getenv("SENTIENTOS_FORGE_LOCK_TTL_SECONDS", "7200")))
    lock_payload = _load_json(root / ".forge/forge.lock")

    started_at = lock_payload.get("started_at") if isinstance(lock_payload.get("started_at"), str) else None
    started_dt = _parse_iso(started_at)
    lock_age: int | None = None
    lock_active = False
    if started_dt is not None:
        lock_age = max(0, int((datetime.now(timezone.utc) - started_dt).total_seconds()))
        lock_active = lock_age <= lock_ttl

    queue = ForgeQueue(pulse_root=root / "pulse")
    receipts = queue.recent_receipts(limit=2000)

    max_runs_day = max(1, int(os.getenv("SENTIENTOS_FORGE_MAX_RUNS_PER_DAY", "2")))
    max_runs_hour = max(1, int(os.getenv("SENTIENTOS_FORGE_MAX_RUNS_PER_HOUR", "1")))
    max_files_day = max(1, int(os.getenv("SENTIENTOS_FORGE_MAX_FILES_CHANGED_PER_DAY", "200")))

    now = datetime.now(timezone.utc)
    day_floor = now - timedelta(days=1)
    hour_floor = now - timedelta(hours=1)

    finished = [receipt for receipt in receipts if receipt.status in {"success", "failed"}]
    finished_with_ts = [(receipt, _parse_iso(receipt.finished_at)) for receipt in finished]
    runs_day = sum(1 for _, parsed in finished_with_ts if parsed is not None and parsed >= day_floor)
    runs_hour = sum(1 for _, parsed in finished_with_ts if parsed is not None and parsed >= hour_floor)
    files_day = sum(_files_changed(root, receipt.report_path) for receipt, parsed in finished_with_ts if parsed is not None and parsed >= day_floor)

    request_id = lock_payload.get("request_id") if isinstance(lock_payload.get("request_id"), str) else None
    goal = lock_payload.get("goal") if isinstance(lock_payload.get("goal"), str) else None
    if request_id and goal is None:
        goal = _goal_for_request(queue, request_id)

    last_receipt: dict[str, Any] | None = None
    if receipts:
        item = receipts[-1]
        last_receipt = {
            "request_id": item.request_id,
            "status": item.status,
            "report_path": item.report_path,
            "error": item.error,
            "finished_at": item.finished_at,
        }

    sentinel_summary = ContractSentinel(repo_root=root).summary()
    last_trigger_domain = _last_trigger_domain(root, queue)
    last_quarantine = _last_quarantine(root)

    return ForgeStatus(
        daemon_enabled=daemon_enabled,
        lock_active=lock_active,
        lock_owner_pid=int(lock_payload["pid"]) if isinstance(lock_payload.get("pid"), int) else None,
        lock_age_seconds=lock_age,
        lock_ttl_seconds=lock_ttl,
        current_request_id=request_id,
        current_goal=goal,
        started_at=started_at,
        runs_remaining_day=max(0, max_runs_day - runs_day),
        runs_remaining_hour=max(0, max_runs_hour - runs_hour),
        files_remaining_day=max(0, max_files_day - files_day),
        last_receipt=last_receipt,
        sentinel_enabled=bool(sentinel_summary.get("sentinel_enabled", False)),
        sentinel_last_enqueued=sentinel_summary.get("sentinel_last_enqueued") if isinstance(sentinel_summary.get("sentinel_last_enqueued"), dict) else None,
        sentinel_state={str(k): v for k, v in sentinel_summary.get("sentinel_state", {}).items()} if isinstance(sentinel_summary.get("sentinel_state"), dict) else {},
        last_trigger_domain=last_trigger_domain,
        last_quarantine=last_quarantine,
    )


def _files_changed(repo_root: Path, report_path: str | None) -> int:
    if not report_path:
        return 0
    payload = _load_json((repo_root / report_path) if not Path(report_path).is_absolute() else Path(report_path))
    budget = payload.get("baseline_budget")
    if not isinstance(budget, dict):
        return 0
    total = budget.get("total_files_changed")
    return total if isinstance(total, int) else 0


def _goal_for_request(queue: ForgeQueue, request_id: str) -> str | None:
    for request in queue.pending_requests():
        if request.request_id == request_id:
            return request.goal
    return None


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)



def _last_quarantine(repo_root: Path) -> dict[str, Any] | None:
    files = sorted((repo_root / "glow/forge").glob("quarantine_*.json"), key=lambda item: item.name)
    if not files:
        return None
    payload = _load_json(files[-1])
    payload["path"] = str(files[-1].relative_to(repo_root))
    return payload

def _last_trigger_domain(repo_root: Path, queue: ForgeQueue) -> str | None:
    queue_path = repo_root / "pulse/forge_queue.jsonl"
    try:
        lines = queue_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    requests: dict[str, dict[str, Any]] = {}
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("request_id"), str):
            requests[str(payload["request_id"])] = payload
    for receipt in reversed(queue.recent_receipts(limit=300)):
        req = requests.get(receipt.request_id)
        if not isinstance(req, dict):
            continue
        metadata = req.get("metadata")
        if req.get("requested_by") != "ContractSentinel" or not isinstance(metadata, dict):
            continue
        domain = metadata.get("trigger_domain")
        if isinstance(domain, str):
            return domain
    return None
