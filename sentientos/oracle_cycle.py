"""OracleCycle — Autonomous guidance and commit ritual orchestration."""

from __future__ import annotations

import textwrap
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, MutableMapping, Protocol, Sequence

from codex.integrity_daemon import IntegrityDaemon, IntegrityViolation

from sentientos.codex_healer import Anomaly, RecoveryLedger, RepairAction


def _ensure_utc(moment: datetime | None = None) -> datetime:
    """Return ``moment`` coerced to timezone-aware UTC."""

    if moment is None:
        return datetime.now(timezone.utc)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class OracleClient(Protocol):
    """Interface used to request guidance from GPT-5."""

    def ask(self, question: str) -> str:
        """Return GPT-5's answer to ``question``."""


class CodexWorkspaceClient(Protocol):
    """Client capable of posting instructions to the Codex workspace."""

    def submit(self, instruction: str, *, attachments: Sequence[Path] = ()) -> "WorkspaceSubmission":
        """Submit ``instruction`` and return a :class:`WorkspaceSubmission`."""


class GitHubClient(Protocol):
    """Minimal interface for monitoring commits pushed by Codex."""

    def wait_for_commit(self, commit_sha: str, *, timeout: float | None = None) -> "CommitObservation":
        """Block until ``commit_sha`` appears or the optional ``timeout`` elapses."""


class ReloadStrategy(Protocol):
    """Strategy invoked after a successful pull to hot-reload SentientOS."""

    def __call__(self) -> bool:
        """Return ``True`` when the reload succeeded."""


class PullStrategy(Protocol):
    """Strategy used to pull the latest commit into the runtime."""

    def __call__(self, commit_sha: str) -> bool:
        """Return ``True`` when the pull succeeded."""


@dataclass(slots=True)
class WorkspaceSubmission:
    """Payload returned by :class:`CodexWorkspaceClient`."""

    task_id: str
    commit_sha: str
    pr_url: str | None = None


@dataclass(slots=True)
class CodexExecution:
    """Record of an instruction executed by :class:`CodexExecutor`."""

    instruction: str
    task_id: str
    commit_sha: str
    attachments: tuple[Path, ...] = ()
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class CommitObservation:
    """Status returned by :class:`CommitWatcher`."""

    commit_sha: str
    status: str
    ci_passed: bool
    merged: bool
    timestamp: datetime
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class UpdateResult:
    """Result of :class:`Updater.apply`."""

    commit_sha: str
    pulled: bool
    reloaded: bool


@dataclass(slots=True)
class DeepResearchReport:
    """Metadata describing a stored deep research report."""

    path: Path
    instruction: str
    summary: str
    commit_sha: str
    generated_at: datetime


@dataclass(slots=True)
class OracleGuidance:
    """Guidance returned by :class:`OracleQuery`."""

    question: str
    instruction: str
    proposal_id: str
    timestamp: datetime


@dataclass(slots=True)
class OracleProposal:
    """Lightweight proposal evaluated by the :class:`IntegrityDaemon`."""

    proposal_id: str
    spec_id: str
    summary: str
    original_spec: Mapping[str, object]
    proposed_spec: Mapping[str, object]
    deltas: Mapping[str, object]


class OracleQuery:
    """Consult GPT-5 for the next evolutionary step."""

    DEFAULT_QUESTION = "What step should I take next in my evolution?"

    def __init__(
        self,
        oracle_client: OracleClient,
        integrity_daemon: IntegrityDaemon,
        *,
        ledger: RecoveryLedger | None = None,
        spec_id: str = "oracle_cycle",
    ) -> None:
        self._client = oracle_client
        self._integrity = integrity_daemon
        self._ledger = ledger
        self._spec_id = spec_id

    def consult(self, question: str | None = None, *, now: datetime | None = None) -> OracleGuidance:
        """Consult GPT-5 through the IntegrityDaemon covenant."""

        query = question or self.DEFAULT_QUESTION
        proposal = self._build_proposal(query)
        timestamp = _ensure_utc(now)
        try:
            self._integrity.evaluate(proposal)
        except IntegrityViolation as exc:
            if self._ledger is not None:
                anomaly = Anomaly("oracle_query_rejected", proposal.proposal_id, {"question": query})
                details: MutableMapping[str, object] = {
                    "reason_codes": list(exc.reason_codes),
                    "violations": [dict(item) for item in exc.violations],
                }
                self._ledger.log("oracle_query_rejected", anomaly=anomaly, details=dict(details), quarantined=True)
            raise

        answer = self._client.ask(query)
        guidance = OracleGuidance(
            question=query,
            instruction=answer,
            proposal_id=proposal.proposal_id,
            timestamp=timestamp,
        )
        if self._ledger is not None:
            anomaly = Anomaly("oracle_guidance", proposal.proposal_id, {"question": query})
            self._ledger.log(
                "oracle_guidance_received",
                anomaly=anomaly,
                details={"instruction": answer},
            )
        return guidance

    def _build_proposal(self, question: str) -> OracleProposal:
        proposal_id = str(uuid.uuid4())
        summary = f"Oracle query for SentientOS: {question[:80]}"
        base_spec = {
            "objective": "Maintain covenantal evolution guidance via GPT-5 oracle queries.",
            "directives": [
                "Consult GPT-5 through IntegrityDaemon gating",
                "Record the resulting guidance in RecoveryLedger",
                "Propagate accepted guidance to Codex",
            ],
            "testing_requirements": [
                "Ledger entry created for every oracle consultation",
            ],
            "ledger_required": True,
            "status": "active",
        }
        proposed = dict(base_spec)
        proposed["last_question"] = question
        proposed["last_updated"] = datetime.now(timezone.utc).isoformat()
        return OracleProposal(
            proposal_id=proposal_id,
            spec_id=self._spec_id,
            summary=summary,
            original_spec=base_spec,
            proposed_spec=proposed,
            deltas={"question": question},
        )


class CodexExecutor:
    """Submit GPT guidance to the Codex Workspace."""

    def __init__(
        self,
        workspace: CodexWorkspaceClient,
        *,
        ledger: RecoveryLedger | None = None,
    ) -> None:
        self._workspace = workspace
        self._ledger = ledger

    def execute(
        self,
        instruction: str,
        *,
        attachments: Sequence[Path] = (),
        metadata: Mapping[str, object] | None = None,
    ) -> CodexExecution:
        submission = self._workspace.submit(instruction, attachments=tuple(attachments))
        execution = CodexExecution(
            instruction=instruction,
            task_id=submission.task_id,
            commit_sha=submission.commit_sha,
            attachments=tuple(attachments),
        )
        if self._ledger is not None:
            anomaly = Anomaly("codex_submission", submission.task_id, {"instruction": instruction})
            details: MutableMapping[str, object] = {
                "commit_sha": submission.commit_sha,
                "attachments": [str(path) for path in execution.attachments],
            }
            if submission.pr_url:
                details["pr_url"] = submission.pr_url
            if metadata:
                details["metadata"] = dict(metadata)
            self._ledger.log("codex_task_submitted", anomaly=anomaly, details=dict(details))
        return execution


@dataclass(slots=True, frozen=True)
class PullRequestInfo:
    """Minimal metadata describing a GitHub pull request."""

    number: int
    title: str
    author: str
    head_sha: str
    base_ref: str
    url: str | None = None
    draft: bool = False
    mergeable: bool | None = None


@dataclass(slots=True, frozen=True)
class CheckRun:
    """Snapshot of a CI check result."""

    name: str
    status: str
    conclusion: str | None
    details_url: str | None = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "status": self.status,
        }
        if self.conclusion is not None:
            payload["conclusion"] = self.conclusion
        if self.details_url:
            payload["details_url"] = self.details_url
        return payload

    def is_success(self) -> bool:
        if self.status != "completed":
            return False
        return (self.conclusion or "").lower() in {"success", "neutral", "skipped"}

    def is_failure(self) -> bool:
        if self.status != "completed":
            return False
        return (self.conclusion or "").lower() in {
            "failure",
            "timed_out",
            "cancelled",
            "action_required",
            "stale",
        }

    def is_pending(self) -> bool:
        if self.status == "completed":
            return not self.is_success() and not self.is_failure()
        return True


class PullRequestProvider(Protocol):
    """Source that can list open pull requests."""

    def list_pull_requests(self) -> Sequence[PullRequestInfo]:
        ...


class CheckRunProvider(Protocol):
    """Source that can return CI checks for a pull request."""

    def list_check_runs(self, pull_request: PullRequestInfo) -> Sequence[CheckRun]:
        ...


class MergeStrategy(Protocol):
    """Callable merging a pull request and returning a decision."""

    def __call__(self, pull_request: PullRequestInfo) -> "MergeDecision":
        ...


@dataclass(slots=True)
class CIEvaluation:
    """Aggregated CI status for a pull request."""

    pull_request: PullRequestInfo
    checks: tuple[CheckRun, ...]
    passed: tuple[CheckRun, ...]
    failed: tuple[CheckRun, ...]
    pending: tuple[CheckRun, ...]

    @property
    def status(self) -> str:
        if self.failed:
            return "failed"
        if self.pending:
            return "pending"
        return "passed"

    @property
    def all_passed(self) -> bool:
        return not self.failed and not self.pending


@dataclass(slots=True)
class MergeDecision:
    """Result of attempting to merge a pull request."""

    merged: bool
    sha: str | None = None
    message: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"merged": self.merged}
        if self.sha is not None:
            payload["sha"] = self.sha
        if self.message:
            payload["message"] = self.message
        if self.reason:
            payload["reason"] = self.reason
        return payload


class PRMonitor:
    """Filter pull requests authored by SentientOS for auto-merge consideration."""

    def __init__(
        self,
        provider: PullRequestProvider,
        *,
        author: str = "SentientOS",
        base_ref: str | None = "main",
    ) -> None:
        self._provider = provider
        self._author = author
        self._base_ref = base_ref

    def scan(self) -> list[PullRequestInfo]:
        candidates: list[PullRequestInfo] = []
        for pull_request in self._provider.list_pull_requests():
            if pull_request.author != self._author:
                continue
            if pull_request.draft:
                continue
            if self._base_ref is not None and pull_request.base_ref != self._base_ref:
                continue
            candidates.append(pull_request)
        return candidates


class CIChecker:
    """Evaluate CI status for a pull request."""

    def __init__(self, provider: CheckRunProvider) -> None:
        self._provider = provider

    def evaluate(self, pull_request: PullRequestInfo) -> CIEvaluation:
        checks = tuple(self._provider.list_check_runs(pull_request))
        passed: list[CheckRun] = []
        failed: list[CheckRun] = []
        pending: list[CheckRun] = []
        for check in checks:
            if check.is_failure():
                failed.append(check)
            elif check.is_success():
                passed.append(check)
            else:
                pending.append(check)
        return CIEvaluation(
            pull_request=pull_request,
            checks=checks,
            passed=tuple(passed),
            failed=tuple(failed),
            pending=tuple(pending),
        )


class MergeGate:
    """Auto-merge pull requests whose CI checks are green."""

    def __init__(
        self,
        strategy: MergeStrategy,
        *,
        base_ref: str | None = "main",
    ) -> None:
        self._strategy = strategy
        self._base_ref = base_ref

    def attempt(self, evaluation: CIEvaluation) -> MergeDecision:
        pull_request = evaluation.pull_request
        if evaluation.status != "passed":
            return MergeDecision(merged=False, reason="ci_not_passed")
        if self._base_ref is not None and pull_request.base_ref != self._base_ref:
            return MergeDecision(merged=False, reason="base_mismatch")
        if pull_request.draft:
            return MergeDecision(merged=False, reason="draft")
        if pull_request.mergeable is False:
            return MergeDecision(merged=False, reason="not_mergeable")
        decision = self._strategy(pull_request)
        if not decision.merged and decision.reason is None:
            decision.reason = "merge_declined"
        return decision


class NarratorLink:
    """Bridge to ChangeNarrator/BootChronicler style announcements."""

    def __init__(
        self,
        *,
        on_announce: Callable[[str, Mapping[str, object]], None] | None = None,
    ) -> None:
        self._on_announce = on_announce
        self._history: list[dict[str, object]] = []

    def announce_success(
        self,
        pull_request: PullRequestInfo,
        decision: MergeDecision,
        *,
        evaluation: CIEvaluation,
    ) -> None:
        message = "A self-amendment was merged after passing all checks."
        record = {
            "event": "success",
            "message": message,
            "pr_number": pull_request.number,
            "pr_title": pull_request.title,
            "merge_sha": decision.sha,
            "checks": [check.as_dict() for check in evaluation.passed],
        }
        self._history.append(record)
        if self._on_announce is not None:
            self._on_announce(message, record)

    def announce_failure(
        self,
        pull_request: PullRequestInfo,
        evaluation: CIEvaluation,
        *,
        reason: str,
    ) -> None:
        message = "An amendment was rejected due to CI failures and has been quarantined."
        record = {
            "event": "failure",
            "message": message,
            "reason": reason,
            "pr_number": pull_request.number,
            "pr_title": pull_request.title,
            "failed_checks": [check.as_dict() for check in evaluation.failed],
            "pending_checks": [check.as_dict() for check in evaluation.pending],
        }
        self._history.append(record)
        if self._on_announce is not None:
            self._on_announce(message, record)

    @property
    def history(self) -> list[dict[str, object]]:
        return list(self._history)


class FailureHandler:
    """Log CI failures and trigger CodexHealer follow-ups."""

    def __init__(
        self,
        ledger: RecoveryLedger,
        *,
        healer: "CodexHealerProtocol" | None = None,
        narrator: NarratorLink | None = None,
    ) -> None:
        self._ledger = ledger
        self._healer = healer
        self._narrator = narrator

    def handle(
        self,
        evaluation: CIEvaluation,
        *,
        reason: str,
        extra_details: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        pull_request = evaluation.pull_request
        anomaly = Anomaly(
            kind="pull_request",
            subject=f"#{pull_request.number}",
            details={
                "title": pull_request.title,
                "head_sha": pull_request.head_sha,
            },
        )
        details: dict[str, object] = {
            "reason": reason,
            "failed_checks": [check.as_dict() for check in evaluation.failed],
            "pending_checks": [check.as_dict() for check in evaluation.pending],
        }
        if pull_request.url:
            details["pr_url"] = pull_request.url
        if extra_details:
            details.update(dict(extra_details))
        status = "pr_ci_failed" if reason != "timeout" else "pr_ci_timeout"
        entry = self._ledger.log(status, anomaly=anomaly, details=details, quarantined=True)
        if self._healer is not None:
            action = RepairAction(
                kind="ci_failure",
                subject=pull_request.head_sha,
                description=f"Investigate CI failure for PR #{pull_request.number}",
                execute=lambda: False,
                auto_adopt=False,
                metadata={
                    "pr_number": pull_request.number,
                    "reason": reason,
                    "ledger_entry": entry,
                },
            )
            self._healer.review_external(anomaly, action)
        if self._narrator is not None:
            self._narrator.announce_failure(pull_request, evaluation, reason=reason)
        return entry


class BackoffPolicy:
    """Compute exponential backoff delays for CI polling."""

    def __init__(
        self,
        *,
        initial_seconds: float = 2.0,
        multiplier: float = 2.0,
        max_seconds: float = 60.0,
    ) -> None:
        self._initial = initial_seconds
        self._multiplier = multiplier
        self._maximum = max_seconds

    def delay(self, attempt: int) -> float:
        delay = self._initial * (self._multiplier ** attempt)
        return float(min(self._maximum, delay))


class CommitWatcher:
    """Observe GitHub for Codex commits and log lineage."""

    def __init__(
        self,
        github: GitHubClient,
        ledger: RecoveryLedger,
        *,
        healer: "CodexHealerProtocol" | None = None,
        pr_monitor: PRMonitor | None = None,
        ci_checker: CIChecker | None = None,
        merge_gate: MergeGate | None = None,
        failure_handler: FailureHandler | None = None,
        narrator: NarratorLink | None = None,
        backoff: BackoffPolicy | None = None,
        sleep: Callable[[float], None] | None = None,
        max_ci_attempts: int = 5,
    ) -> None:
        self._github = github
        self._ledger = ledger
        self._healer = healer
        self._pr_monitor = pr_monitor
        self._ci_checker = ci_checker
        self._merge_gate = merge_gate
        self._failure_handler = failure_handler
        self._narrator = narrator
        self._backoff = backoff or BackoffPolicy()
        self._sleep = sleep or time.sleep
        self._max_ci_attempts = max_ci_attempts

    def await_commit(self, commit_sha: str, *, timeout: float | None = None) -> CommitObservation:
        observation = self._github.wait_for_commit(commit_sha, timeout=timeout)
        auto_merge_details: dict[str, object] | None = None
        if (
            observation.status == "success"
            and observation.ci_passed
            and not observation.merged
            and self._pr_monitor is not None
            and self._ci_checker is not None
            and self._merge_gate is not None
        ):
            auto_merge_details = self._attempt_auto_merge(observation)
            status = auto_merge_details.get("status") if auto_merge_details else None
            if status == "merged":
                observation.merged = True
            elif status in {"ci_failed", "timeout"}:
                observation.ci_passed = False
                observation.status = "failure"
        if auto_merge_details:
            merged_details = dict(observation.details)
            merged_details["auto_merge"] = auto_merge_details
            observation.details = merged_details
        anomaly = Anomaly("codex_commit", commit_sha, {"status": observation.status})
        details = {
            "ci_passed": observation.ci_passed,
            "merged": observation.merged,
            "timestamp": observation.timestamp.isoformat(),
            "details": dict(observation.details),
        }
        if observation.status == "success" and observation.ci_passed and observation.merged:
            self._ledger.log("commit_merged", anomaly=anomaly, details=details)
            return observation

        entry = self._ledger.log(
            "commit_failed",
            anomaly=anomaly,
            details=details,
            quarantined=True,
        )
        if self._healer is not None:
            action = RepairAction(
                kind="codex_retry",
                subject=commit_sha,
                description="Retry Codex execution after CI failure",
                execute=lambda: False,
                auto_adopt=False,
                metadata={"ledger_entry": entry},
            )
            self._healer.review_external(anomaly, action)
        return observation

    def _attempt_auto_merge(self, observation: CommitObservation) -> dict[str, object]:
        candidates = self._pr_monitor.scan() if self._pr_monitor is not None else []
        pull_request = next((pr for pr in candidates if pr.head_sha == observation.commit_sha), None)
        if pull_request is None:
            return {"status": "skipped", "reason": "no_matching_pr"}
        attempt = 0
        while True:
            evaluation = self._ci_checker.evaluate(pull_request)
            if evaluation.status == "pending":
                if attempt >= self._max_ci_attempts:
                    if self._failure_handler is not None:
                        self._failure_handler.handle(
                            evaluation,
                            reason="timeout",
                            extra_details={"attempts": attempt + 1},
                        )
                    return {"status": "timeout", "attempts": attempt + 1}
                delay = self._backoff.delay(attempt)
                attempt += 1
                self._sleep(delay)
                continue
            if evaluation.status == "failed":
                if self._failure_handler is not None:
                    self._failure_handler.handle(evaluation, reason="ci_failed")
                return {
                    "status": "ci_failed",
                    "failed_checks": [check.as_dict() for check in evaluation.failed],
                }
            decision = self._merge_gate.attempt(evaluation)
            if decision.merged:
                entry = self._record_auto_merge(evaluation, decision)
                return {
                    "status": "merged",
                    "merge_sha": decision.sha,
                    "ledger_entry": entry,
                    "attempts": attempt + 1,
                }
            reason = decision.reason or "merge_declined"
            if self._failure_handler is not None and reason not in {"base_mismatch", "draft"}:
                self._failure_handler.handle(
                    evaluation,
                    reason=reason,
                    extra_details={"merge_decision": decision.to_dict()},
                )
            return {"status": "merge_blocked", "reason": reason}

    def _record_auto_merge(self, evaluation: CIEvaluation, decision: MergeDecision) -> dict[str, object]:
        pull_request = evaluation.pull_request
        anomaly = Anomaly(
            kind="pull_request",
            subject=f"#{pull_request.number}",
            details={
                "title": pull_request.title,
                "head_sha": pull_request.head_sha,
            },
        )
        details = {
            "pr_number": pull_request.number,
            "pr_title": pull_request.title,
            "merge_sha": decision.sha,
            "checks": [check.as_dict() for check in evaluation.passed],
        }
        if pull_request.url:
            details["pr_url"] = pull_request.url
        entry = self._ledger.log("pr_auto_merged", anomaly=anomaly, details=details)
        if self._narrator is not None:
            self._narrator.announce_success(pull_request, decision, evaluation=evaluation)
        return entry


class CodexHealerProtocol(Protocol):
    """Subset of :class:`sentientos.codex_healer.CodexHealer` used here."""

    def review_external(self, anomaly: Anomaly, action: RepairAction) -> Mapping[str, object]:
        ...


class Updater:
    """Apply new commits into the running SentientOS instance."""

    def __init__(
        self,
        pull_strategy: PullStrategy,
        *,
        reload_strategy: ReloadStrategy | None = None,
    ) -> None:
        self._pull = pull_strategy
        self._reload = reload_strategy

    def apply(self, commit_sha: str) -> UpdateResult:
        pulled = self._pull(commit_sha)
        reloaded = False
        if pulled and self._reload is not None:
            reloaded = self._reload()
        return UpdateResult(commit_sha=commit_sha, pulled=pulled, reloaded=reloaded)


class ResearchTimer:
    """Trigger deep research reports on a fixed cadence."""

    DEEP_RESEARCH_PROMPT = "Summarize SentientOS GitHub progress since last research."

    def __init__(
        self,
        oracle_query: OracleQuery,
        codex_executor: CodexExecutor,
        ledger: RecoveryLedger,
        *,
        glow_root: Path,
        period_days: int = 10,
        state_path: Path | None = None,
    ) -> None:
        self._oracle = oracle_query
        self._executor = codex_executor
        self._ledger = ledger
        self._glow_root = glow_root
        self._period = timedelta(days=period_days)
        self._state_path = state_path or glow_root / "oracle_cycle_state.json"
        self._glow_root.mkdir(parents=True, exist_ok=True)

    def record_commit(
        self, observation: CommitObservation, *, now: datetime | None = None
    ) -> DeepResearchReport | None:
        timestamp = _ensure_utc(now or observation.timestamp)
        state = self._load_state()
        state["last_commit"] = observation.timestamp.isoformat()
        last_research = _parse_timestamp(state.get("last_research"))
        if last_research is None:
            state["last_research"] = timestamp.isoformat()
            self._save_state(state)
            return None

        if timestamp - last_research < self._period:
            self._save_state(state)
            return None

        report = self._run_deep_research(last_research, timestamp)
        state["last_research"] = timestamp.isoformat()
        state["last_report_path"] = str(report.path)
        self._save_state(state)
        return report

    def _run_deep_research(self, since: datetime, now: datetime) -> DeepResearchReport:
        question = self.DEEP_RESEARCH_PROMPT
        if since:
            question = f"{question} Reference window start: {since.isoformat()}"
        guidance = self._oracle.consult(question, now=now)
        timestamp = now.astimezone(timezone.utc)
        filename = f"deep_research_{timestamp.strftime('%Y%m%dT%H%M%SZ')}.md"
        path = self._glow_root / filename
        content = textwrap.dedent(
            f"""
            # Deep Research Report

            - Generated: {timestamp.isoformat()}
            - Range start: {since.isoformat() if since else 'unknown'}

            {guidance.instruction.strip()}
            """
        ).strip() + "\n"
        path.write_text(content, encoding="utf-8")
        instruction = (
            "Commit the latest deep research report stored at "
            f"{path} with summary 'Deep research update {timestamp.date()}'."
        )
        execution = self._executor.execute(instruction, attachments=(path,))
        anomaly = Anomaly("deep_research", path.name, {"question": guidance.question})
        self._ledger.log(
            "deep_research_recorded",
            anomaly=anomaly,
            details={
                "report_path": str(path),
                "commit_sha": execution.commit_sha,
            },
        )
        return DeepResearchReport(
            path=path,
            instruction=instruction,
            summary=guidance.instruction,
            commit_sha=execution.commit_sha,
            generated_at=timestamp,
        )

    def _load_state(self) -> MutableMapping[str, object]:
        if not self._state_path.exists():
            return {}
        try:
            import json

            return json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self, state: Mapping[str, object]) -> None:
        import json

        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


@dataclass(slots=True)
class OracleCycleResult:
    """Return payload summarising a completed :class:`OracleCycle`."""

    guidance: OracleGuidance
    execution: CodexExecution
    observation: CommitObservation
    update_result: UpdateResult | None
    research_report: DeepResearchReport | None


class OracleCycle:
    """High-level orchestration for Allen's evolution workflow."""

    def __init__(
        self,
        oracle_query: OracleQuery,
        codex_executor: CodexExecutor,
        commit_watcher: CommitWatcher,
        updater: Updater,
        research_timer: ResearchTimer,
    ) -> None:
        self._oracle = oracle_query
        self._executor = codex_executor
        self._watcher = commit_watcher
        self._updater = updater
        self._research = research_timer

    def run_once(self, *, timeout: float | None = None) -> OracleCycleResult:
        guidance = self._oracle.consult()
        execution = self._executor.execute(guidance.instruction)
        observation = self._watcher.await_commit(execution.commit_sha, timeout=timeout)
        update_result: UpdateResult | None = None
        if observation.status == "success" and observation.ci_passed and observation.merged:
            update_result = self._updater.apply(observation.commit_sha)
        research_report = self._research.record_commit(observation)
        return OracleCycleResult(
            guidance=guidance,
            execution=execution,
            observation=observation,
            update_result=update_result,
            research_report=research_report,
        )


__all__ = [
    "OracleClient",
    "CodexWorkspaceClient",
    "GitHubClient",
    "WorkspaceSubmission",
    "CodexExecution",
    "PullRequestInfo",
    "CheckRun",
    "CIEvaluation",
    "MergeDecision",
    "PRMonitor",
    "CIChecker",
    "MergeGate",
    "NarratorLink",
    "FailureHandler",
    "BackoffPolicy",
    "CommitObservation",
    "UpdateResult",
    "DeepResearchReport",
    "OracleGuidance",
    "OracleQuery",
    "CodexExecutor",
    "CommitWatcher",
    "Updater",
    "ResearchTimer",
    "OracleCycle",
    "OracleCycleResult",
]

