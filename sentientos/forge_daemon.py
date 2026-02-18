"""Autonomous executor for queued CathedralForge requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import contextlib
import json
import logging
import os
from pathlib import Path

from sentientos.cathedral_forge import CathedralForge, ForgeReport
from sentientos.contract_sentinel import ContractSentinel
from sentientos.event_stream import record as record_event, record_forge_event
from sentientos.forge_index import update_index_incremental
from sentientos.forge_queue import ForgeQueue, ForgeRequest

LOGGER = logging.getLogger(__name__)
POLICY_PATH = Path("glow/forge/policy.json")


@dataclass(slots=True)
class ForgeGovernor:
    max_runs_per_day: int = 2
    max_runs_per_hour: int = 1
    max_files_changed_per_day: int = 200

    @classmethod
    def from_env(cls) -> ForgeGovernor:
        return cls(
            max_runs_per_day=max(1, int(os.getenv("SENTIENTOS_FORGE_MAX_RUNS_PER_DAY", "2"))),
            max_runs_per_hour=max(1, int(os.getenv("SENTIENTOS_FORGE_MAX_RUNS_PER_HOUR", "1"))),
            max_files_changed_per_day=max(1, int(os.getenv("SENTIENTOS_FORGE_MAX_FILES_CHANGED_PER_DAY", "200"))),
        )


class ForgeDaemon:
    def __init__(
        self,
        *,
        queue: ForgeQueue | None = None,
        forge: CathedralForge | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.queue = queue or ForgeQueue()
        self.forge = forge or CathedralForge(repo_root=self.repo_root)
        self.lock_path = self.repo_root / ".forge" / "forge.lock"
        self.lock_ttl_seconds = max(60, int(os.getenv("SENTIENTOS_FORGE_LOCK_TTL_SECONDS", "7200")))
        self.governor = ForgeGovernor.from_env()
        self.policy = _load_policy(self.repo_root / POLICY_PATH)

    def run_tick(self) -> None:
        if os.getenv("SENTIENTOS_FORGE_DAEMON_ENABLED", "0") != "1":
            return
        if self._is_lock_active():
            self._emit_forge_event(status="lock_skip", request=None, message="ForgeDaemon tick skipped: active forge lock")
            self._emit("ForgeDaemon tick skipped: active forge lock")
            return

        request = self.queue.next_request()
        if request is None:
            return

        policy_error = self._validate_request_policy(request)
        if policy_error:
            self.queue.mark_finished(
                request.request_id,
                status="rejected_policy",
                report_path=None,
                error=policy_error,
            )
            self._emit_forge_event(status="rejected_policy", request=request, error=policy_error)
            self._emit(f"ForgeDaemon policy rejected request {request.request_id}: {policy_error}", level="warning")
            return

        if not self._within_budget(request):
            self.queue.mark_finished(
                request.request_id,
                status="skipped_budget",
                report_path=None,
                error="daemon budget exhausted",
            )
            self._emit_forge_event(status="skipped_budget", request=request, error="daemon budget exhausted")
            self._emit(f"ForgeDaemon budget gate skipped request {request.request_id}", level="warning")
            return

        started_at = _iso_now()
        self._write_lock(request)
        self.queue.mark_started(request.request_id, started_at=started_at)
        self._emit_forge_event(status="started", request=request)
        self._emit(f"ForgeDaemon running request {request.request_id} ({request.goal})")

        try:
            sentinel_triggered = bool(request.metadata.get("sentinel_triggered"))
            prev_allow = os.environ.get("SENTIENTOS_FORGE_ALLOW_AUTOPUBLISH")
            prev_sent = os.environ.get("SENTIENTOS_FORGE_SENTINEL_TRIGGERED")
            prev_sent_allow = os.environ.get("SENTIENTOS_FORGE_SENTINEL_ALLOW_AUTOPUBLISH")
            os.environ["SENTIENTOS_FORGE_ALLOW_AUTOPUBLISH"] = "1" if bool(request.autopublish_flags.get("auto_publish")) else "0"
            os.environ["SENTIENTOS_FORGE_SENTINEL_TRIGGERED"] = "1" if sentinel_triggered else "0"
            os.environ["SENTIENTOS_FORGE_SENTINEL_ALLOW_AUTOPUBLISH"] = "1" if bool(request.autopublish_flags.get("sentinel_allow_autopublish")) else "0"
            report = self.forge.run(request.goal)
            if prev_allow is None:
                os.environ.pop("SENTIENTOS_FORGE_ALLOW_AUTOPUBLISH", None)
            else:
                os.environ["SENTIENTOS_FORGE_ALLOW_AUTOPUBLISH"] = prev_allow
            if prev_sent is None:
                os.environ.pop("SENTIENTOS_FORGE_SENTINEL_TRIGGERED", None)
            else:
                os.environ["SENTIENTOS_FORGE_SENTINEL_TRIGGERED"] = prev_sent
            if prev_sent_allow is None:
                os.environ.pop("SENTIENTOS_FORGE_SENTINEL_ALLOW_AUTOPUBLISH", None)
            else:
                os.environ["SENTIENTOS_FORGE_SENTINEL_ALLOW_AUTOPUBLISH"] = prev_sent_allow
            pr_metadata_path = _extract_pr_metadata_path(report.notes)
            report_path = str(self.forge._report_path(report.generated_at))
            status = "success" if report.outcome == "success" else "failed"
            error = "\n".join(report.failure_reasons) if report.failure_reasons else None
            self.queue.mark_finished(
                request.request_id,
                status=status,
                started_at=started_at,
                report_path=report_path,
                docket_path=report.docket_path,
                commit_sha=report.git_sha or None,
                pr_metadata_path=pr_metadata_path,
                error=error,
            )
            self._emit_forge_event(status=status, request=request, report_path=report_path, error=error)
            if bool(request.metadata.get("sentinel_triggered")) and report.transaction_status in {"quarantined", "rolled_back"}:
                domain = request.metadata.get("trigger_domain")
                if isinstance(domain, str):
                    sentinel = ContractSentinel(repo_root=self.repo_root, queue=self.queue)
                    sentinel.note_quarantine(domain=domain, quarantine_ref=report.quarantine_ref, reasons=report.regression_reasons or report.failure_reasons)
            if status != "success":
                self._maybe_requeue(request, report)
            self._emit(f"ForgeDaemon completed {request.request_id} with status={status}")
        except Exception as exc:  # pragma: no cover - defensive runtime path
            self.queue.mark_finished(
                request.request_id,
                status="failed",
                started_at=started_at,
                report_path=None,
                error=str(exc),
            )
            self._emit_forge_event(status="failed", request=request, error=str(exc))
            self._emit(f"ForgeDaemon failed request {request.request_id}: {exc}", level="error")
        finally:
            self._clear_lock()

    def _validate_request_policy(self, request: ForgeRequest) -> str | None:
        allowed_goals = self.policy.get("allowlisted_goal_ids")
        if isinstance(allowed_goals, list):
            goal_id = request.goal_id or request.goal
            if goal_id not in {item for item in allowed_goals if isinstance(item, str)}:
                return f"goal_id_not_allowlisted:{goal_id}"

        allowed_flags = self.policy.get("allowlisted_autopublish_flags")
        if isinstance(allowed_flags, list):
            allowed_set = {item for item in allowed_flags if isinstance(item, str)}
            for key in request.autopublish_flags:
                if key not in allowed_set:
                    return f"autopublish_flag_not_allowlisted:{key}"

        max_budget = self.policy.get("max_budget")
        if isinstance(max_budget, dict) and request.max_budget_overrides:
            for key, value in request.max_budget_overrides.items():
                cap = max_budget.get(key)
                if isinstance(cap, int) and value > cap:
                    return f"budget_override_exceeds_policy:{key}>{cap}"
        return None

    def _within_budget(self, request: ForgeRequest) -> bool:
        now = datetime.now(timezone.utc)
        receipts = self.queue.recent_receipts(limit=400)
        successes = [receipt for receipt in receipts if receipt.status in {"success", "failed"}]
        hour_floor = now - timedelta(hours=1)
        day_floor = now - timedelta(days=1)

        runs_in_hour = sum(1 for receipt in successes if _is_in_window(receipt.finished_at, hour_floor))
        if runs_in_hour >= self.governor.max_runs_per_hour:
            return False

        runs_in_day = sum(1 for receipt in successes if _is_in_window(receipt.finished_at, day_floor))
        if runs_in_day >= self.governor.max_runs_per_day:
            return False

        files_changed_today = sum(self._receipt_files_changed(receipt) for receipt in successes if _is_in_window(receipt.finished_at, day_floor))
        if files_changed_today >= self.governor.max_files_changed_per_day:
            return False

        if request.goal_id == "baseline_reclamation":
            baseline_cap = int(os.getenv("SENTIENTOS_FORGE_DAEMON_BASELINE_MAX_ITERS", "2"))
            if baseline_cap < 1:
                return False
        return True

    def _receipt_files_changed(self, receipt: object) -> int:
        if not hasattr(receipt, "report_path"):
            return 0
        report_path = getattr(receipt, "report_path")
        if not isinstance(report_path, str) or not report_path:
            return 0
        payload = _load_json(Path(report_path))
        budget = payload.get("baseline_budget")
        if isinstance(budget, dict):
            total = budget.get("total_files_changed")
            if isinstance(total, int):
                return total
        return 0

    def _maybe_requeue(self, request: ForgeRequest, report: ForgeReport) -> None:
        retry_enabled = bool(request.autopublish_flags.get("retry_on_failure"))
        if not retry_enabled:
            return
        lineage = request.autopublish_flags.get("lineage", [])
        if not isinstance(lineage, list):
            lineage = []
        if request.request_id in lineage:
            return
        if report.goal_id.startswith("forge_"):
            return

        latest = self.queue.recent_receipts(limit=50)
        for receipt in reversed(latest):
            if receipt.request_id == request.request_id and receipt.status == "failed":
                finished_at = _parse_iso(receipt.finished_at)
                if finished_at and datetime.now(timezone.utc) - finished_at < timedelta(minutes=30):
                    return
                break

        cloned = ForgeRequest(
            request_id="",
            goal=request.goal,
            goal_id=request.goal_id,
            requested_by="forge_daemon_retry",
            priority=request.priority + 1,
            autopublish_flags={**request.autopublish_flags, "lineage": [*lineage, request.request_id]},
            max_budget_overrides=request.max_budget_overrides,
        )
        self.queue.enqueue(cloned)

    def _is_lock_active(self) -> bool:
        if not self.lock_path.exists():
            return False
        payload = _load_json(self.lock_path)
        started = _parse_iso(str(payload.get("started_at", "")))
        if started is None:
            return True
        if datetime.now(timezone.utc) - started > timedelta(seconds=self.lock_ttl_seconds):
            self._clear_lock()
            return False
        return True

    def _write_lock(self, request: ForgeRequest) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text(
            json.dumps({"request_id": request.request_id, "goal": request.goal, "started_at": _iso_now(), "pid": os.getpid()}, sort_keys=True),
            encoding="utf-8",
        )

    def _clear_lock(self) -> None:
        with contextlib.suppress(OSError):
            self.lock_path.unlink()

    def _emit(self, message: str, *, level: str = "info") -> None:
        log_level = getattr(LOGGER, level, LOGGER.info)
        log_level(message)
        record_event(message, level=level)

    def _emit_forge_event(
        self,
        *,
        status: str,
        request: ForgeRequest | None,
        report_path: str | None = None,
        error: str | None = None,
        message: str | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "event": "forge_daemon",
            "status": status,
            "request_id": request.request_id if request else None,
            "goal_id": request.goal_id if request else None,
            "goal": request.goal if request else None,
            "report_path": report_path,
            "error": error,
            "message": message or status,
            "level": "warning" if status in {"rejected_policy", "skipped_budget", "lock_skip"} else "info",
        }
        record_forge_event(payload)
        update_index_incremental(self.repo_root, event=payload)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_pr_metadata_path(notes: list[str]) -> str | None:
    for note in notes:
        if note.startswith("autopr_metadata:"):
            return note.split(":", 1)[1]
    return None


def _is_in_window(value: str | None, floor: datetime) -> bool:
    parsed = _parse_iso(value)
    return parsed is not None and parsed >= floor


def _load_policy(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "allowlisted_goal_ids": ["forge_smoke_noop", "baseline_reclamation", "repo_green_storm"],
            "allowlisted_autopublish_flags": [],
            "max_budget": {},
        }
    return payload if isinstance(payload, dict) else {}
