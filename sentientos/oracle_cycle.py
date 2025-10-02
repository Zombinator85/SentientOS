"""OracleCycle — Autonomous guidance and commit ritual orchestration."""

from __future__ import annotations

import textwrap
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


class CommitWatcher:
    """Observe GitHub for Codex commits and log lineage."""

    def __init__(
        self,
        github: GitHubClient,
        ledger: RecoveryLedger,
        *,
        healer: "CodexHealerProtocol" | None = None,
    ) -> None:
        self._github = github
        self._ledger = ledger
        self._healer = healer

    def await_commit(self, commit_sha: str, *, timeout: float | None = None) -> CommitObservation:
        observation = self._github.wait_for_commit(commit_sha, timeout=timeout)
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

