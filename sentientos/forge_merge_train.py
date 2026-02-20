from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Protocol

from sentientos.event_stream import record_forge_event
from sentientos.forge_outcomes import summarize_report
from sentientos.forge_progress_contract import emit_forge_progress_contract
from sentientos.forge_queue import ForgeQueue
from sentientos.github_checks import PRRef, fetch_pr_checks, wait_for_pr_checks
from sentientos.github_merge import GitHubMergeOps, MergeResult, RebaseResult


STATE_PATH = Path("glow/forge/merge_train.json")
EVENTS_PATH = Path("pulse/forge_train_events.jsonl")
POLICY_PATH = Path("glow/forge/merge_train_policy.json")
DOCKET_PREFIX = "merge_train_docket"


@dataclass(slots=True)
class TrainPolicy:
    enabled: bool = False
    base_branch: str = "main"
    max_active_prs: int = 3
    max_rebase_attempts: int = 2
    max_check_retries: int = 1
    merge_strategy: str = "squash"
    cooldown_minutes_on_failure: int = 60
    require_clean_transaction: bool = True


@dataclass(slots=True)
class TrainEntry:
    run_id: str
    pr_url: str
    pr_number: int | None
    head_sha: str
    branch: str
    goal_id: str | None
    campaign_id: str | None
    status: str
    created_at: str
    updated_at: str
    check_overall: str
    rebase_attempts: int = 0
    check_retries: int = 0
    last_error: str | None = None


@dataclass(slots=True)
class TrainState:
    entries: list[TrainEntry] = field(default_factory=list)
    last_merged_pr: str | None = None
    last_failure_at: str | None = None


class ForgeGitHubOps(Protocol):
    def checks_for(self, entry: TrainEntry) -> tuple[str, str | None, str | None]:
        ...

    def wait_for_checks(self, entry: TrainEntry, timeout_seconds: int = 1800) -> tuple[str, bool]:
        ...

    def is_branch_behind_base(self, entry: TrainEntry, base_branch: str) -> bool:
        ...

    def rebase_branch(self, entry: TrainEntry, base_branch: str) -> RebaseResult:
        ...

    def merge_pull_request(self, entry: TrainEntry, strategy: str) -> MergeResult:
        ...


class DefaultForgeGitHubOps:
    def __init__(self, repo_root: Path) -> None:
        self._merge = GitHubMergeOps(repo_root=repo_root)

    def checks_for(self, entry: TrainEntry) -> tuple[str, str | None, str | None]:
        checks = fetch_pr_checks(pr_number=entry.pr_number, pr_url=entry.pr_url or None, head_sha=entry.head_sha)
        return checks.overall, checks.pr.head_sha or None, checks.pr.branch or None

    def wait_for_checks(self, entry: TrainEntry, timeout_seconds: int = 1800) -> tuple[str, bool]:
        pr_ref = PRRef(number=entry.pr_number, url=entry.pr_url, head_sha=entry.head_sha, branch=entry.branch, created_at=entry.created_at)
        checks, timing = wait_for_pr_checks(pr_ref, timeout_seconds=max(60, timeout_seconds), poll_interval_seconds=20)
        return checks.overall, bool(timing.get("timed_out", False))

    def is_branch_behind_base(self, entry: TrainEntry, base_branch: str) -> bool:
        return self._merge.is_branch_behind_base(entry=entry, base_branch=base_branch)

    def rebase_branch(self, entry: TrainEntry, base_branch: str) -> RebaseResult:
        return self._merge.rebase_branch(entry=entry, base_branch=base_branch)

    def merge_pull_request(self, entry: TrainEntry, strategy: str) -> MergeResult:
        return self._merge.merge_pull_request(entry=entry, strategy=strategy)


class ForgeMergeTrain:
    def __init__(self, repo_root: Path | None = None, *, queue: ForgeQueue | None = None, github_ops: ForgeGitHubOps | None = None) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.queue = queue or ForgeQueue(pulse_root=self.repo_root / "pulse")
        self.github_ops: ForgeGitHubOps = github_ops or DefaultForgeGitHubOps(self.repo_root)
        self.state_path = self.repo_root / STATE_PATH
        self.events_path = self.repo_root / EVENTS_PATH
        self.policy_path = self.repo_root / POLICY_PATH
        self.lock_path = self.repo_root / ".forge/train.lock"

    def load_policy(self) -> TrainPolicy:
        policy = TrainPolicy()
        payload = _load_json(self.policy_path)
        if payload:
            try:
                policy = TrainPolicy(**{k: v for k, v in payload.items() if k in TrainPolicy.__dataclass_fields__})
            except TypeError:
                policy = TrainPolicy()
        env_enabled = os.getenv("SENTIENTOS_FORGE_TRAIN_ENABLED")
        if env_enabled is not None:
            policy.enabled = env_enabled == "1"
        default_branch = os.getenv("SENTIENTOS_FORGE_BASE_BRANCH")
        if default_branch:
            policy.base_branch = default_branch
        return policy

    def save_policy(self, policy: TrainPolicy) -> None:
        self.policy_path.parent.mkdir(parents=True, exist_ok=True)
        self.policy_path.write_text(json.dumps(asdict(policy), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def load_state(self) -> TrainState:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return TrainState()
        if not isinstance(payload, dict):
            return TrainState()
        raw_entries = payload.get("entries")
        entries: list[TrainEntry] = []
        if isinstance(raw_entries, list):
            for item in raw_entries:
                if not isinstance(item, dict):
                    continue
                try:
                    entries.append(TrainEntry(**item))
                except TypeError:
                    continue
        return TrainState(entries=entries, last_merged_pr=_as_str(payload.get("last_merged_pr")), last_failure_at=_as_str(payload.get("last_failure_at")))

    def save_state(self, state: TrainState) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(asdict(state), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def add_entry_from_publish(self, payload: dict[str, object], *, state: TrainState | None = None) -> TrainState:
        current = state or self.load_state()
        pr_url = _as_str(payload.get("publish_pr_url"))
        if not pr_url:
            return current
        publish_status = _as_str(payload.get("publish_status")) or ""
        checks_overall = _as_str(payload.get("publish_checks_overall")) or publish_status or "unknown"
        if publish_status not in {"ready_to_merge", "held_failed_checks"} and checks_overall not in {"success", "failure", "pending"}:
            return current

        run_id = _as_str(payload.get("provenance_run_id")) or ""
        report_path = _as_str(payload.get("report_path"))
        report_payload = _load_json(self.repo_root / report_path) if report_path else {}
        publish_remote = report_payload.get("publish_remote") if isinstance(report_payload.get("publish_remote"), dict) else {}
        pr_number = _as_int(publish_remote.get("pr_number"))
        if pr_number is None:
            pr_number = _parse_pr_number(pr_url)
        head_sha = _as_str(publish_remote.get("head_sha")) or ""
        branch = _as_str(publish_remote.get("branch")) or ""
        goal_id = _as_str(report_payload.get("goal_id"))
        campaign_id = _as_str(report_payload.get("campaign_id"))
        created_at = _as_str(payload.get("finished_at")) or _iso_now()

        existing = next((entry for entry in current.entries if entry.pr_url == pr_url), None)
        next_status = "ready" if checks_overall == "success" else ("held" if checks_overall == "failure" else "checking")
        if existing is not None:
            existing.updated_at = _iso_now()
            existing.check_overall = checks_overall
            existing.status = next_status if existing.status not in {"merged", "failed"} else existing.status
            if head_sha:
                existing.head_sha = head_sha
            if branch:
                existing.branch = branch
        else:
            current.entries.append(
                TrainEntry(
                    run_id=run_id,
                    pr_url=pr_url,
                    pr_number=pr_number,
                    head_sha=head_sha,
                    branch=branch,
                    goal_id=goal_id,
                    campaign_id=campaign_id,
                    status=next_status,
                    created_at=created_at,
                    updated_at=_iso_now(),
                    check_overall=checks_overall,
                )
            )
            self._emit_event("train_ingest", {"pr_url": pr_url, "status": next_status, "run_id": run_id})
        return current

    def prune_merged(self, keep_last_n: int = 50) -> None:
        state = self.load_state()
        merged = [entry for entry in state.entries if entry.status == "merged"]
        keep_merged = merged[-keep_last_n:]
        keep_ids = {entry.pr_url for entry in keep_merged}
        state.entries = [entry for entry in state.entries if entry.status != "merged" or entry.pr_url in keep_ids]
        self.save_state(state)

    def tick(self) -> dict[str, object]:
        policy = self.load_policy()
        if not policy.enabled:
            return {"status": "disabled"}
        if not self._acquire_lock():
            return {"status": "locked"}
        try:
            state = self.load_state()
            state = self._ingest_receipts(state)
            if not self._within_budget():
                self.save_state(state)
                return {"status": "budget_exhausted", "entries": len(state.entries)}
            active_count = len([item for item in state.entries if item.status in {"queued", "ready", "held", "rebasing", "checking", "mergeable"}])
            if active_count > policy.max_active_prs:
                self.save_state(state)
                return {"status": "max_active_exceeded", "active": active_count, "max_active": policy.max_active_prs}
            candidate = self._select_candidate(state)
            if candidate is None:
                self.save_state(state)
                return {"status": "idle", "entries": len(state.entries)}

            result = self._process_candidate(state, candidate, policy)
            self.save_state(state)
            return result
        finally:
            self._release_lock()

    def hold(self, pr_number: int) -> bool:
        state = self.load_state()
        entry = next((item for item in state.entries if item.pr_number == pr_number), None)
        if entry is None:
            return False
        entry.status = "held"
        entry.updated_at = _iso_now()
        entry.last_error = "manually_held"
        self.save_state(state)
        self._emit_event("train_held", {"pr_number": pr_number})
        return True

    def release(self, pr_number: int) -> bool:
        state = self.load_state()
        entry = next((item for item in state.entries if item.pr_number == pr_number), None)
        if entry is None:
            return False
        entry.status = "ready"
        entry.updated_at = _iso_now()
        entry.last_error = None
        self.save_state(state)
        self._emit_event("train_released", {"pr_number": pr_number})
        return True

    def _ingest_receipts(self, state: TrainState) -> TrainState:
        for receipt in self.queue.recent_receipts(limit=400):
            if receipt.publish_pr_url:
                state = self.add_entry_from_publish(asdict(receipt), state=state)
        return state

    def _select_candidate(self, state: TrainState) -> TrainEntry | None:
        active = [item for item in state.entries if item.status in {"queued", "ready", "held", "rebasing", "checking", "mergeable"}]
        if not active:
            return None
        prefer_improvement = os.getenv("SENTIENTOS_FORGE_TRAIN_PREFER_IMPROVEMENT", "1") == "1"

        def _rank(entry: TrainEntry) -> tuple[int, int, str]:
            pri = 0 if entry.status in {"ready", "mergeable", "checking", "rebasing"} else 1
            improvement_rank = 0
            if prefer_improvement and _is_recovery_entry(entry):
                improvement_rank = self._improvement_rank(entry)
            return (pri, improvement_rank, entry.created_at)

        active.sort(key=_rank)
        return active[0]


    def _improvement_rank(self, entry: TrainEntry) -> int:
        from_contract = self._contract_improvement_rank(entry.run_id)
        if from_contract is not None:
            return from_contract
        report = self._report_for_run_id(entry.run_id)
        if not report:
            return 1
        summary = summarize_report(report)
        improved = (
            summary.last_progress_improved
            or (
                summary.ci_before_failed_count is not None
                and summary.ci_after_failed_count is not None
                and summary.ci_after_failed_count < summary.ci_before_failed_count
            )
            or (summary.progress_delta_percent is not None and summary.progress_delta_percent >= 30.0)
        )
        return 0 if improved else 1

    def _contract_improvement_rank(self, run_id: str) -> int | None:
        if not run_id:
            return None
        path = self.repo_root / "glow/contracts/forge_progress_baseline.json"
        payload = _load_json(path)
        if not payload:
            payload = emit_forge_progress_contract(self.repo_root).to_dict()
        rows = payload.get("last_runs") if isinstance(payload.get("last_runs"), list) else []
        for row in reversed(rows):
            if not isinstance(row, dict):
                continue
            if str(row.get("run_id", "")) != run_id:
                continue
            return 0 if bool(row.get("improved", False)) else 1
        return None

    def _report_for_run_id(self, run_id: str) -> dict[str, object]:
        if not run_id:
            return {}
        reports = sorted((self.repo_root / "glow/forge").glob("report_*.json"), key=lambda item: item.name, reverse=True)
        for path in reports[:300]:
            payload = _load_json(path)
            if str(payload.get("provenance_run_id") or payload.get("run_id") or "") == run_id:
                return payload
        return {}

    def _process_candidate(self, state: TrainState, entry: TrainEntry, policy: TrainPolicy) -> dict[str, object]:
        now = _iso_now()
        entry.updated_at = now

        if entry.status == "held" and state.last_failure_at:
            fail_ts = _parse_iso(state.last_failure_at)
            if fail_ts is not None and datetime.now(timezone.utc) - fail_ts < timedelta(minutes=policy.cooldown_minutes_on_failure):
                return {"status": "cooldown", "pr": entry.pr_url}

        if self.github_ops.is_branch_behind_base(entry, policy.base_branch):
            if entry.rebase_attempts >= policy.max_rebase_attempts:
                entry.status = "held"
                entry.last_error = "rebase_attempts_exhausted"
                state.last_failure_at = now
                self._emit_event("train_rebase_attempted", {"pr_url": entry.pr_url, "status": "exhausted"}, level="warning")
                return {"status": "held", "reason": "rebase_attempts_exhausted", "pr": entry.pr_url}
            entry.status = "rebasing"
            rebase = self.github_ops.rebase_branch(entry, policy.base_branch)
            entry.rebase_attempts += 1
            self._emit_event("train_rebase_attempted", {"pr_url": entry.pr_url, "ok": rebase.ok, "message": rebase.message})
            if not rebase.ok:
                entry.status = "held"
                entry.last_error = "conflict" if rebase.conflict else (rebase.message or "rebase_failed")
                state.last_failure_at = now
                if rebase.conflict:
                    docket = self._write_conflict_docket(entry, rebase)
                    self._emit_event("train_conflict_docket", {"path": docket, "pr_url": entry.pr_url}, level="warning")
                return {"status": "held", "reason": entry.last_error, "pr": entry.pr_url}
            if rebase.new_head_sha:
                entry.head_sha = rebase.new_head_sha

        entry.status = "checking"
        check_overall, refreshed_head, refreshed_branch = self.github_ops.checks_for(entry)
        self._emit_event("train_checks_polled", {"pr_url": entry.pr_url, "overall": check_overall})
        entry.check_overall = check_overall
        if refreshed_head:
            entry.head_sha = refreshed_head
        if refreshed_branch:
            entry.branch = refreshed_branch

        if check_overall in {"pending", "unknown"}:
            final_overall, timed_out = self.github_ops.wait_for_checks(entry)
            entry.check_overall = final_overall
            self._emit_event("train_checks_polled", {"pr_url": entry.pr_url, "overall": final_overall, "timed_out": timed_out})
            if timed_out:
                entry.status = "held"
                entry.last_error = "checks_timeout"
                state.last_failure_at = now
                return {"status": "held", "reason": "checks_timeout", "pr": entry.pr_url}

        if entry.check_overall == "failure":
            entry.check_retries += 1
            if entry.check_retries > policy.max_check_retries:
                entry.status = "failed"
                entry.last_error = "checks_failed"
            else:
                entry.status = "held"
                entry.last_error = "checks_failed_retry"
            state.last_failure_at = now
            return {"status": entry.status, "reason": entry.last_error, "pr": entry.pr_url}

        if entry.check_overall != "success":
            entry.status = "held"
            entry.last_error = "checks_unknown"
            return {"status": "held", "reason": "checks_unknown", "pr": entry.pr_url}

        audit_gate = self._audit_integrity_gate(entry)
        if audit_gate is not None:
            entry.status = "held"
            entry.last_error = "audit_integrity_failed"
            docket = self._write_audit_hold_docket(entry=entry, gate=audit_gate)
            self._emit_event("train_audit_integrity_hold", {"pr_url": entry.pr_url, "docket": docket, "failing_fields": audit_gate["failing_fields"]}, level="warning")
            return {"status": "held", "reason": "audit_integrity_failed", "pr": entry.pr_url}

        entry.status = "mergeable"
        allow_merge = os.getenv("SENTIENTOS_FORGE_AUTOMERGE", "0") == "1"
        if os.getenv("SENTIENTOS_FORGE_SENTINEL_TRIGGERED", "0") == "1" and os.getenv("SENTIENTOS_FORGE_SENTINEL_ALLOW_AUTOMERGE", "0") != "1":
            allow_merge = False
        if not allow_merge:
            return {"status": "mergeable", "pr": entry.pr_url}

        merge = self.github_ops.merge_pull_request(entry, policy.merge_strategy)
        self._emit_event("train_merge_attempted", {"pr_url": entry.pr_url, "ok": merge.ok, "message": merge.message})
        if merge.ok:
            entry.status = "merged"
            entry.last_error = None
            state.last_merged_pr = entry.pr_url
            self._emit_event("train_merge_outcome", {"pr_url": entry.pr_url, "outcome": "merged"})
            return {"status": "merged", "pr": entry.pr_url}

        entry.status = "held" if merge.conflict else "failed"
        entry.last_error = "conflict" if merge.conflict else (merge.message or "merge_failed")
        state.last_failure_at = now
        self._emit_event("train_merge_outcome", {"pr_url": entry.pr_url, "outcome": entry.status, "error": entry.last_error}, level="warning")
        if merge.conflict:
            docket = self._write_conflict_docket(entry, RebaseResult(ok=False, conflict=True, message=merge.message, new_head_sha=None, suspect_files=[]))
            self._emit_event("train_conflict_docket", {"path": docket, "pr_url": entry.pr_url}, level="warning")
        return {"status": entry.status, "pr": entry.pr_url, "reason": entry.last_error}

    def _audit_integrity_gate(self, entry: TrainEntry) -> dict[str, object] | None:
        doctrine = self._load_doctrine_for_entry(entry)
        failures = _audit_integrity_failures(doctrine)
        if not failures:
            return None
        return {
            "failing_fields": failures,
            "doctor_report_path": _latest_path(self.repo_root / "glow/forge", "audit_doctor_*.json"),
            "audit_docket_path": _latest_path(self.repo_root / "glow/forge", "audit_docket_*.json"),
        }

    def _load_doctrine_for_entry(self, entry: TrainEntry) -> dict[str, object]:
        path = self.repo_root / "glow/contracts/stability_doctrine.json"
        payload = _load_json(path)
        if not payload:
            return {}
        sha = _as_str(payload.get("git_sha"))
        if sha and sha != entry.head_sha:
            return payload
        return payload

    def _write_audit_hold_docket(self, *, entry: TrainEntry, gate: dict[str, object]) -> str:
        ts = _iso_now().replace(":", "-")
        target = self.repo_root / "glow/forge" / f"{DOCKET_PREFIX}_{ts}.json"
        payload = {
            "kind": "merge_train_audit_hold",
            "pr_url": entry.pr_url,
            "pr_number": entry.pr_number,
            "head_sha": entry.head_sha,
            "status": "held",
            "last_error": "audit_integrity_failed",
            "failing_fields": gate.get("failing_fields", []),
            "doctor_report_path": gate.get("doctor_report_path"),
            "audit_docket_path": gate.get("audit_docket_path"),
            "suggested_fix": "run audit_integrity_repair",
            "generated_at": _iso_now(),
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return str(target.relative_to(self.repo_root))

    def _within_budget(self) -> bool:
        max_runs_day = max(1, int(os.getenv("SENTIENTOS_FORGE_MAX_RUNS_PER_DAY", "2")))
        max_runs_hour = max(1, int(os.getenv("SENTIENTOS_FORGE_MAX_RUNS_PER_HOUR", "1")))
        now = datetime.now(timezone.utc)
        receipts = self.queue.recent_receipts(limit=400)
        successes = [receipt for receipt in receipts if receipt.status in {"success", "failed"}]
        hour_floor = now - timedelta(hours=1)
        day_floor = now - timedelta(days=1)
        runs_hour = sum(1 for item in successes if _parse_iso(item.finished_at) and _parse_iso(item.finished_at) >= hour_floor)
        runs_day = sum(1 for item in successes if _parse_iso(item.finished_at) and _parse_iso(item.finished_at) >= day_floor)
        return runs_hour < max_runs_hour and runs_day < max_runs_day

    def _emit_event(self, event: str, payload: dict[str, object], *, level: str = "info") -> None:
        row = {"event": event, "timestamp": _iso_now(), **payload}
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        record_forge_event({"event": event, "status": payload.get("status", "ok"), "message": event, "level": level, **payload})

    def _write_conflict_docket(self, entry: TrainEntry, result: RebaseResult) -> str:
        ts = _iso_now().replace(":", "-")
        target = self.repo_root / "glow/forge" / f"{DOCKET_PREFIX}_{ts}.json"
        payload = {
            "pr_url": entry.pr_url,
            "pr_number": entry.pr_number,
            "goal_id": entry.goal_id,
            "campaign_id": entry.campaign_id,
            "last_error": entry.last_error,
            "suspected_conflict_files": result.suspect_files,
            "suggested_strategies": ["re-run rebase with manual conflict resolution", "split large changes into smaller PRs", "merge latest base and retest"],
            "generated_at": _iso_now(),
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return str(target.relative_to(self.repo_root))

    def _acquire_lock(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"pid": os.getpid(), "started_at": _iso_now()}, sort_keys=True))
        return True

    def _release_lock(self) -> None:
        try:
            self.lock_path.unlink()
        except OSError:
            return


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _parse_pr_number(url: str) -> int | None:
    parts = [part for part in url.rstrip("/").split("/") if part]
    if len(parts) >= 2 and parts[-2] == "pull" and parts[-1].isdigit():
        return int(parts[-1])
    return None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")



def _audit_integrity_failures(doctrine: dict[str, object]) -> list[str]:
    if not doctrine:
        return ["stability_doctrine_missing"]
    failures: list[str] = []
    if doctrine.get("baseline_integrity_ok") is False:
        failures.append("baseline_integrity_ok")
    if doctrine.get("runtime_integrity_ok") is False:
        failures.append("runtime_integrity_ok")
    if doctrine.get("baseline_unexpected_change_detected") is True:
        failures.append("baseline_unexpected_change_detected")
    return failures


def _latest_path(root: Path, pattern: str) -> str | None:
    items = sorted(root.glob(pattern), key=lambda item: item.name)
    if not items:
        return None
    return str(items[-1].relative_to(root.parent.parent))

def _is_recovery_entry(entry: TrainEntry) -> bool:
    campaign = entry.campaign_id or ""
    goal = entry.goal_id or ""
    return campaign in {"ci_baseline_recovery", "stability_recovery_full"} or goal in {"repo_green_storm", "audit_integrity_repair", "campaign:ci_baseline_recovery", "campaign:stability_recovery_full"}
