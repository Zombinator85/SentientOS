"""Durable queue and receipt ledger for Forge daemon requests."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import uuid

LOGGER = logging.getLogger(__name__)

PULSE_ROOT = Path("pulse")
QUEUE_PATH = PULSE_ROOT / "forge_queue.jsonl"
RECEIPTS_PATH = PULSE_ROOT / "forge_receipts.jsonl"


@dataclass(slots=True)
class ForgeRequest:
    request_id: str
    goal: str
    goal_id: str | None = None
    requested_at: str = field(default_factory=lambda: _iso_now())
    requested_by: str = "operator"
    priority: int = 100
    autopublish_flags: dict[str, object] = field(default_factory=dict)
    max_budget_overrides: dict[str, int] | None = None


@dataclass(slots=True)
class ForgeReceipt:
    request_id: str
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    report_path: str | None = None
    docket_path: str | None = None
    commit_sha: str | None = None
    pr_metadata_path: str | None = None
    error: str | None = None


class ForgeQueue:
    """Append-only request and receipt ledger with resilient readers."""

    def __init__(self, *, pulse_root: Path | None = None) -> None:
        root = pulse_root or PULSE_ROOT
        self.queue_path = root / QUEUE_PATH.name
        self.receipts_path = root / RECEIPTS_PATH.name

    def enqueue(self, request: ForgeRequest) -> str:
        request_id = request.request_id or self._new_request_id()
        payload = asdict(request)
        payload["request_id"] = request_id
        payload.setdefault("requested_at", _iso_now())
        self._append_jsonl(self.queue_path, payload)
        return request_id

    def next_request(self) -> ForgeRequest | None:
        requests = self._load_requests()
        if not requests:
            return None
        consumed_ids = {receipt.request_id for receipt in self._load_receipts() if receipt.status in {"started", "success", "failed", "skipped_budget"}}
        pending = [request for request in requests if request.request_id not in consumed_ids]
        if not pending:
            return None
        pending.sort(key=lambda req: (req.priority, req.requested_at, req.request_id))
        return pending[0]

    def mark_started(self, request_id: str, *, started_at: str | None = None) -> ForgeReceipt:
        receipt = ForgeReceipt(request_id=request_id, status="started", started_at=started_at or _iso_now())
        self._append_jsonl(self.receipts_path, asdict(receipt))
        return receipt

    def mark_finished(
        self,
        request_id: str,
        *,
        status: str,
        report_path: str | None,
        docket_path: str | None = None,
        commit_sha: str | None = None,
        pr_metadata_path: str | None = None,
        error: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
    ) -> ForgeReceipt:
        receipt = ForgeReceipt(
            request_id=request_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at or _iso_now(),
            report_path=report_path,
            docket_path=docket_path,
            commit_sha=commit_sha,
            pr_metadata_path=pr_metadata_path,
            error=error,
        )
        self._append_jsonl(self.receipts_path, asdict(receipt))
        return receipt

    def prune(self, *, max_age_days: int = 30, keep_last_n: int = 200) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        self._prune_file(self.queue_path, cutoff, keep_last_n, "requested_at")
        self._prune_file(self.receipts_path, cutoff, keep_last_n, "finished_at")

    def recent_receipts(self, *, limit: int = 20) -> list[ForgeReceipt]:
        return self._load_receipts()[-limit:]

    def pending_requests(self) -> list[ForgeRequest]:
        requests = self._load_requests()
        consumed_ids = {receipt.request_id for receipt in self._load_receipts() if receipt.status in {"started", "success", "failed", "skipped_budget"}}
        pending = [request for request in requests if request.request_id not in consumed_ids]
        return sorted(pending, key=lambda req: (req.priority, req.requested_at, req.request_id))

    def _load_requests(self) -> list[ForgeRequest]:
        rows = self._read_jsonl(self.queue_path)
        loaded: list[ForgeRequest] = []
        for row in rows:
            request = _request_from_row(row)
            if request is None:
                LOGGER.warning("forge_queue_bad_entry", extra={"path": str(self.queue_path), "row": row})
                continue
            loaded.append(request)
        return loaded

    def _load_receipts(self) -> list[ForgeReceipt]:
        rows = self._read_jsonl(self.receipts_path)
        loaded: list[ForgeReceipt] = []
        for row in rows:
            receipt = _receipt_from_row(row)
            if receipt is None:
                LOGGER.warning("forge_receipt_bad_entry", extra={"path": str(self.receipts_path), "row": row})
                continue
            loaded.append(receipt)
        return loaded

    def _append_jsonl(self, path: Path, row: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")
        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
        try:
            os.write(fd, encoded)
            os.fsync(fd)
        finally:
            os.close(fd)

    def _read_jsonl(self, path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        rows: list[dict[str, object]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    LOGGER.warning("forge_jsonl_corrupt_line", extra={"path": str(path), "line": line_number})
                    continue
                if not isinstance(payload, dict):
                    LOGGER.warning("forge_jsonl_non_object", extra={"path": str(path), "line": line_number})
                    continue
                rows.append(payload)
        return rows

    def _prune_file(self, path: Path, cutoff: datetime, keep_last_n: int, ts_field: str) -> None:
        rows = self._read_jsonl(path)
        if len(rows) <= keep_last_n:
            return
        recent_rows = rows[-keep_last_n:]
        preserved: list[dict[str, object]] = []
        for row in recent_rows:
            timestamp = row.get(ts_field)
            if not isinstance(timestamp, str):
                preserved.append(row)
                continue
            parsed = _parse_iso(timestamp)
            if parsed is None or parsed >= cutoff:
                preserved.append(row)
        text = "".join(json.dumps(item, sort_keys=True) + "\n" for item in preserved)
        path.write_text(text, encoding="utf-8")

    def _new_request_id(self) -> str:
        return f"forge-{uuid.uuid4().hex[:12]}"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime | None:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _request_from_row(row: dict[str, object]) -> ForgeRequest | None:
    request_id = row.get("request_id")
    goal = row.get("goal")
    if not isinstance(request_id, str) or not isinstance(goal, str):
        return None
    raw_goal_id = row.get("goal_id")
    goal_id: str | None = raw_goal_id if isinstance(raw_goal_id, str) else None
    raw_requested_at = row.get("requested_at")
    requested_at: str = raw_requested_at if isinstance(raw_requested_at, str) else _iso_now()
    raw_requested_by = row.get("requested_by")
    requested_by: str = raw_requested_by if isinstance(raw_requested_by, str) else "operator"
    raw_priority = row.get("priority")
    priority: int = raw_priority if isinstance(raw_priority, int) else 100
    raw_flags = row.get("autopublish_flags")
    autopublish_flags: dict[object, object] = raw_flags if isinstance(raw_flags, dict) else {}
    raw_budget = row.get("max_budget_overrides")
    max_budget_overrides: dict[object, object] | None = raw_budget if isinstance(raw_budget, dict) else None
    return ForgeRequest(
        request_id=request_id,
        goal=goal,
        goal_id=goal_id,
        requested_at=requested_at,
        requested_by=requested_by,
        priority=priority,
        autopublish_flags={str(k): v for k, v in autopublish_flags.items()},
        max_budget_overrides={str(k): int(v) for k, v in max_budget_overrides.items() if isinstance(v, int)} if max_budget_overrides else None,
    )


def _receipt_from_row(row: dict[str, object]) -> ForgeReceipt | None:
    request_id = row.get("request_id")
    status = row.get("status")
    if not isinstance(request_id, str) or not isinstance(status, str):
        return None
    def _opt(name: str) -> str | None:
        value = row.get(name)
        return value if isinstance(value, str) else None
    return ForgeReceipt(
        request_id=request_id,
        status=status,
        started_at=_opt("started_at"),
        finished_at=_opt("finished_at"),
        report_path=_opt("report_path"),
        docket_path=_opt("docket_path"),
        commit_sha=_opt("commit_sha"),
        pr_metadata_path=_opt("pr_metadata_path"),
        error=_opt("error"),
    )
