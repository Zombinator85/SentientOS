"""Durable queue and receipt ledger for Forge daemon requests."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import stat
import uuid
from contextlib import contextmanager
from typing import Iterator
try:
    import fcntl
except ImportError:  # Windows must fail closed until a safe writer is available.
    fcntl = None  # type: ignore[assignment]

from sentientos.event_stream import record_forge_event
from sentientos.private_file_custody import (
    PrivateFileCustodyError,
    open_private_directory,
    replace_private_bytes_with_status,
)
from sentientos.windows_handle_custody import WindowsHandleCustodyError, read_explicit_file

LOGGER = logging.getLogger(__name__)

PULSE_ROOT = Path("pulse")
QUEUE_PATH = PULSE_ROOT / "forge_queue.jsonl"
RECEIPTS_PATH = PULSE_ROOT / "forge_receipts.jsonl"
MAX_RECEIPT_LEDGER_BYTES = 1_048_576
MAX_RECEIPT_LEDGER_ROWS = 4096
MAX_QUEUE_LEDGER_BYTES = 1_048_576
MAX_QUEUE_LEDGER_ROWS = 4096
MAX_QUEUE_LEDGER_ROW_BYTES = 65_536


class ForgeReceiptLedgerError(RuntimeError):
    """Receipt custody is incomplete or cannot be safely reconstructed."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ForgeQueueCustodyError(RuntimeError):
    """A queue/receipt append could not preserve local file custody."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


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
    metadata: dict[str, object] = field(default_factory=dict)


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
    provenance_run_id: str | None = None
    provenance_path: str | None = None
    publish_status: str | None = None
    publish_pr_url: str | None = None
    publish_checks_overall: str | None = None
    has_drift: bool | None = None
    drift_domains: list[str] | None = None
    contract_alert_badge: str | None = None
    contract_alert_reason: str | None = None
    contract_alert_counts: dict[str, int] | None = None
    contract_row_summary_counts: dict[str, int] | None = None


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
        record_forge_event(
            {
                "event": "forge_queue",
                "status": "enqueued",
                "request_id": request_id,
                "goal_id": payload.get("goal_id"),
                "goal": payload.get("goal"),
                "message": "enqueued",
                "level": "info",
            }
        )
        return request_id

    def next_request(self) -> ForgeRequest | None:
        requests = self._load_requests()
        if not requests:
            return None
        consumed_ids = {receipt.request_id for receipt in self._load_receipts() if receipt.status in {"started", "success", "failed", "skipped_budget", "rejected_policy", "rejected_quarantine_custody"}}
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
        provenance_run_id: str | None = None,
        provenance_path: str | None = None,
        publish_status: str | None = None,
        publish_pr_url: str | None = None,
        publish_checks_overall: str | None = None,
        has_drift: bool | None = None,
        drift_domains: list[str] | None = None,
        contract_alert_badge: str | None = None,
        contract_alert_reason: str | None = None,
        contract_alert_counts: dict[str, int] | None = None,
        contract_row_summary_counts: dict[str, int] | None = None,
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
            provenance_run_id=provenance_run_id,
            provenance_path=provenance_path,
            publish_status=publish_status,
            publish_pr_url=publish_pr_url,
            publish_checks_overall=publish_checks_overall,
            has_drift=has_drift,
            drift_domains=drift_domains,
            contract_alert_badge=contract_alert_badge,
            contract_alert_reason=contract_alert_reason,
            contract_alert_counts=contract_alert_counts,
            contract_row_summary_counts=contract_row_summary_counts,
        )
        self._append_jsonl(self.receipts_path, asdict(receipt))
        return receipt

    def prune(self, *, max_age_days: int = 30, keep_last_n: int = 200) -> None:
        if (type(max_age_days) is not int or max_age_days < 0
                or type(keep_last_n) is not int or not 1 <= keep_last_n <= MAX_QUEUE_LEDGER_ROWS):
            raise ForgeQueueCustodyError("ledger_prune_bounds_invalid")
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        with self._writer_lock():
            # Validate both owners before publication. Then prune requests
            # first: if interrupted between replacements, extra receipts are
            # inert, while removing a receipt for a retained request could
            # cause replay. The stable owner lock excludes appends while the
            # two files are reconciled.
            queue_rows = self._read_request_jsonl(strict=True)
            receipt_rows = self._read_receipt_rows()
            retained_queue = _pruned_rows(queue_rows, cutoff, keep_last_n, "requested_at")
            retained_request_ids = {
                request_id for row in retained_queue
                if isinstance((request_id := row.get("request_id")), str)
            }
            ordinary_receipt_indexes = _pruned_row_indexes(
                receipt_rows, cutoff, keep_last_n, "finished_at"
            )
            # Preserve the complete ordered receipt chain for every request
            # retained in the queue. For removed requests, retain only rows
            # selected by the ordinary age/count policy. Index-based filtering
            # preserves ordering and repeated identical rows.
            retained_receipts = [
                row for index, row in enumerate(receipt_rows)
                if row.get("request_id") in retained_request_ids
                or index in ordinary_receipt_indexes
            ]
            if retained_queue != queue_rows:
                self._replace_jsonl(self.queue_path, retained_queue)
            if retained_receipts != receipt_rows:
                self._replace_jsonl(self.receipts_path, retained_receipts)

    def recent_receipts(self, *, limit: int = 20) -> list[ForgeReceipt]:
        return self._load_receipts()[-limit:]

    def pending_requests(self) -> list[ForgeRequest]:
        requests = self._load_requests()
        consumed_ids = {receipt.request_id for receipt in self._load_receipts() if receipt.status in {"started", "success", "failed", "skipped_budget", "rejected_policy", "rejected_quarantine_custody"}}
        pending = [request for request in requests if request.request_id not in consumed_ids]
        return sorted(pending, key=lambda req: (req.priority, req.requested_at, req.request_id))

    def _load_requests(self) -> list[ForgeRequest]:
        rows = self._read_request_jsonl()
        loaded: list[ForgeRequest] = []
        for row in rows:
            request = _request_from_row(row)
            if request is None:
                LOGGER.warning("forge_queue_bad_entry", extra={"path": str(self.queue_path), "row": row})
                continue
            loaded.append(request)
        return loaded

    def _read_request_jsonl(self, *, strict: bool = False) -> list[dict[str, object]]:
        try:
            raw = read_explicit_file(
                self.queue_path,
                max_bytes=MAX_QUEUE_LEDGER_BYTES,
                require_private_acl=False,
            )
        except WindowsHandleCustodyError as exc:
            custody_code = str(exc)
            if custody_code == "explicit_file_missing":
                return []
            raise ForgeQueueCustodyError(f"queue_custody_{custody_code}") from exc
        except OSError as exc:
            raise ForgeQueueCustodyError("queue_custody_unavailable") from exc
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ForgeQueueCustodyError("queue_ledger_encoding_invalid") from exc
        rows: list[dict[str, object]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            if len(rows) >= MAX_QUEUE_LEDGER_ROWS:
                raise ForgeQueueCustodyError("queue_ledger_row_limit_exceeded")
            try:
                payload = json.loads(
                    line,
                    object_pairs_hook=_unique_json_object,
                    parse_constant=_reject_json_constant,
                )
            except (json.JSONDecodeError, ValueError, RecursionError) as exc:
                if strict:
                    raise ForgeQueueCustodyError(
                        f"queue_ledger_json_invalid:{line_number}"
                    ) from exc
                LOGGER.warning("forge_queue_corrupt_line", extra={"line": line_number})
                continue
            if not isinstance(payload, dict):
                if strict:
                    raise ForgeQueueCustodyError(
                        f"queue_ledger_record_not_object:{line_number}"
                    )
                LOGGER.warning("forge_queue_non_object_line", extra={"line": line_number})
                continue
            if strict and _request_from_row(payload) is None:
                raise ForgeQueueCustodyError(
                    f"queue_ledger_identity_invalid:{line_number}"
                )
            rows.append(payload)
        return rows

    def _load_receipts(self) -> list[ForgeReceipt]:
        rows = self._read_receipt_rows()
        loaded: list[ForgeReceipt] = []
        for line_number, row in enumerate(rows, start=1):
            receipt = _receipt_from_row(row)
            if receipt is None:
                raise ForgeReceiptLedgerError(
                    f"receipt_ledger_identity_invalid:{line_number}"
                )
            loaded.append(receipt)
        return loaded

    def _read_receipt_rows(self) -> list[dict[str, object]]:
        try:
            raw = read_explicit_file(
                self.receipts_path,
                max_bytes=MAX_RECEIPT_LEDGER_BYTES,
                require_private_acl=False,
            )
        except WindowsHandleCustodyError as exc:
            custody_code = str(exc)
            if custody_code == "explicit_file_missing":
                return []
            raise ForgeReceiptLedgerError(f"receipt_custody_{custody_code}") from exc
        except OSError as exc:
            raise ForgeReceiptLedgerError("receipt_custody_unavailable") from exc
        rows: list[dict[str, object]] = []
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ForgeReceiptLedgerError("receipt_ledger_encoding_invalid") from exc
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            if len(rows) >= MAX_RECEIPT_LEDGER_ROWS:
                raise ForgeReceiptLedgerError("receipt_ledger_row_limit_exceeded")
            try:
                payload = json.loads(
                    line,
                    object_pairs_hook=_unique_json_object,
                    parse_constant=_reject_json_constant,
                )
            except (json.JSONDecodeError, ValueError, RecursionError) as exc:
                raise ForgeReceiptLedgerError(
                    f"receipt_ledger_json_invalid:{line_number}"
                ) from exc
            if not isinstance(payload, dict):
                raise ForgeReceiptLedgerError(
                    f"receipt_ledger_record_not_object:{line_number}"
                )
            if _receipt_from_row(payload) is None:
                raise ForgeReceiptLedgerError(
                    f"receipt_ledger_identity_invalid:{line_number}"
                )
            rows.append(payload)
        return rows

    def _replace_jsonl(self, path: Path, rows: list[dict[str, object]]) -> None:
        encoded = b"".join(
            (json.dumps(row, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
            for row in rows
        )
        if len(encoded) > MAX_QUEUE_LEDGER_BYTES:
            raise ForgeQueueCustodyError("ledger_prune_byte_limit_exceeded")
        try:
            durable = replace_private_bytes_with_status(
                path, encoded, max_bytes=MAX_QUEUE_LEDGER_BYTES,
            )
        except PrivateFileCustodyError as exc:
            raise ForgeQueueCustodyError(f"ledger_prune_{exc.code}") from exc
        if not durable:
            raise ForgeQueueCustodyError("ledger_prune_durability_uncertain")

    @contextmanager
    def _writer_lock(self) -> Iterator[int]:
        if (os.name != "posix" or fcntl is None or not hasattr(os, "O_NOFOLLOW")
                or not hasattr(os, "pread")):
            raise ForgeQueueCustodyError("ledger_writer_lock_unsupported")
        try:
            directory_fd = open_private_directory(self.queue_path.parent, create=True)
        except PrivateFileCustodyError as exc:
            raise ForgeQueueCustodyError(f"ledger_directory_{exc.code}") from exc
        lock_fd: int | None = None
        locked = False
        try:
            try:
                lock_fd = os.open(
                    ".forge_queue.lock",
                    os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                    dir_fd=directory_fd,
                )
                metadata = os.fstat(lock_fd)
                if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                        or metadata.st_nlink != 1 or metadata.st_mode & 0o022):
                    raise ForgeQueueCustodyError("ledger_writer_lock_custody_invalid")
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                locked = True
                os.fsync(directory_fd)
            except ForgeQueueCustodyError:
                raise
            except OSError as exc:
                raise ForgeQueueCustodyError("ledger_writer_lock_unavailable") from exc
            yield directory_fd
        finally:
            try:
                if lock_fd is not None:
                    if locked:
                        try:
                            fcntl.flock(lock_fd, fcntl.LOCK_UN)
                        except OSError:
                            pass
                    os.close(lock_fd)
            finally:
                os.close(directory_fd)

    def _append_jsonl(self, path: Path, row: dict[str, object]) -> None:
        if (os.name != "posix" or fcntl is None or not hasattr(os, "O_NOFOLLOW")
                or not hasattr(os, "pread")):
            raise ForgeQueueCustodyError("ledger_append_unsupported")
        try:
            encoded = (json.dumps(row, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        except (TypeError, ValueError, RecursionError) as exc:
            raise ForgeQueueCustodyError("ledger_record_not_canonical_json") from exc
        if len(encoded) > MAX_QUEUE_LEDGER_ROW_BYTES:
            raise ForgeQueueCustodyError("ledger_record_too_large")
        fd: int | None = None
        with self._writer_lock() as directory_fd:
            try:
                fd = os.open(
                    path.name,
                    os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW
                    | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                    dir_fd=directory_fd,
                )
                metadata = os.fstat(fd)
                if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                        or metadata.st_nlink != 1 or metadata.st_mode & 0o022):
                    raise ForgeQueueCustodyError("ledger_file_custody_invalid")
                if metadata.st_size + len(encoded) > MAX_QUEUE_LEDGER_BYTES:
                    raise ForgeQueueCustodyError("ledger_byte_limit_exceeded")
                existing = bytearray()
                offset = 0
                while offset < metadata.st_size:
                    chunk = os.pread(fd, min(65_536, metadata.st_size - offset), offset)
                    if not chunk:
                        raise ForgeQueueCustodyError("ledger_existing_read_incomplete")
                    existing.extend(chunk)
                    offset += len(chunk)
                try:
                    existing.decode("utf-8", errors="strict")
                except UnicodeDecodeError as exc:
                    raise ForgeQueueCustodyError("ledger_existing_encoding_invalid") from exc
                if existing and not existing.endswith(b"\n"):
                    raise ForgeQueueCustodyError("ledger_existing_tail_incomplete")
                existing_rows = sum(bool(line.strip()) for line in existing.splitlines())
                if existing_rows >= MAX_QUEUE_LEDGER_ROWS:
                    raise ForgeQueueCustodyError("ledger_row_limit_exceeded")
                view = memoryview(encoded)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise ForgeQueueCustodyError("ledger_append_incomplete")
                    view = view[written:]
                os.fsync(fd)
                os.fsync(directory_fd)
            except ForgeQueueCustodyError:
                raise
            except OSError as exc:
                # A short/failed append can leave a partial line; the strict
                # receipt reader will then block request selection on restart.
                raise ForgeQueueCustodyError("ledger_append_durability_uncertain") from exc
            finally:
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError as exc:
                        raise ForgeQueueCustodyError(
                            "ledger_append_close_uncertain"
                        ) from exc
                    fd = None

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


def _pruned_row_indexes(
    rows: list[dict[str, object]], cutoff: datetime, keep_last_n: int, ts_field: str,
) -> set[int]:
    if len(rows) <= keep_last_n:
        return set(range(len(rows)))
    retained: set[int] = set()
    for index in range(len(rows) - keep_last_n, len(rows)):
        timestamp = rows[index].get(ts_field)
        parsed = _parse_iso(timestamp) if isinstance(timestamp, str) else None
        if not isinstance(timestamp, str) or parsed is None or parsed >= cutoff:
            retained.add(index)
    return retained


def _pruned_rows(
    rows: list[dict[str, object]], cutoff: datetime, keep_last_n: int, ts_field: str,
) -> list[dict[str, object]]:
    indexes = _pruned_row_indexes(rows, cutoff, keep_last_n, ts_field)
    return [row for index, row in enumerate(rows) if index in indexes]


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
    raw_metadata = row.get("metadata")
    metadata: dict[object, object] = raw_metadata if isinstance(raw_metadata, dict) else {}
    return ForgeRequest(
        request_id=request_id,
        goal=goal,
        goal_id=goal_id,
        requested_at=requested_at,
        requested_by=requested_by,
        priority=priority,
        autopublish_flags={str(k): v for k, v in autopublish_flags.items()},
        max_budget_overrides={str(k): int(v) for k, v in max_budget_overrides.items() if isinstance(v, int)} if max_budget_overrides else None,
        metadata={str(k): v for k, v in metadata.items()},
    )


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise ValueError("nonstandard_json_constant")


def _receipt_from_row(row: dict[str, object]) -> ForgeReceipt | None:
    request_id = row.get("request_id")
    status = row.get("status")
    if not isinstance(request_id, str) or not isinstance(status, str):
        return None
    def _opt(name: str) -> str | None:
        value = row.get(name)
        return value if isinstance(value, str) else None
    raw_domains = row.get("drift_domains")
    drift_domains = [str(item) for item in raw_domains if isinstance(item, str)] if isinstance(raw_domains, list) else None
    raw_alert_counts = row.get("contract_alert_counts")
    alert_counts = {str(k): int(v) for k, v in raw_alert_counts.items() if isinstance(v, int)} if isinstance(raw_alert_counts, dict) else None
    raw_row_counts = row.get("contract_row_summary_counts")
    row_counts = {str(k): int(v) for k, v in raw_row_counts.items() if isinstance(v, int)} if isinstance(raw_row_counts, dict) else None
    raw_has_drift = row.get("has_drift")
    has_drift = raw_has_drift if isinstance(raw_has_drift, bool) else None
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
        provenance_run_id=_opt("provenance_run_id"),
        provenance_path=_opt("provenance_path"),
        publish_status=_opt("publish_status"),
        publish_pr_url=_opt("publish_pr_url"),
        publish_checks_overall=_opt("publish_checks_overall"),
        has_drift=has_drift,
        drift_domains=drift_domains,
        contract_alert_badge=_opt("contract_alert_badge"),
        contract_alert_reason=_opt("contract_alert_reason"),
        contract_alert_counts=alert_counts,
        contract_row_summary_counts=row_counts,
    )
