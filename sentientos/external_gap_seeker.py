"""External gap seeking via Codex Workspace automation.

This module provides a thin orchestration layer that asks the Codex Workspace
agent to audit the SentientOS repository for TODO markers, unimplemented
stubs, missing tests, type errors and other coverage gaps.  The collaboration
is intentionally narrow: generate a precise natural-language instruction,
relay it to Codex, watch for the resulting commit, pull the update and narrate
what happened in the :class:`~sentientos.codex_healer.RecoveryLedger`.

The workflow mirrors the high-level design documented in the repo audit brief::

    OracleGapRequest -> CodexRelay -> CommitWatcher -> UpdaterLink -> NarrativeMark

All components are designed to be easily faked in tests so daemons can exercise
this loop without network or GitHub access during CI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, MutableMapping, Sequence

from codex.gap_seeker import GapResolution

from sentientos.codex_healer import Anomaly, RecoveryLedger
from sentientos.oracle_cycle import (
    CodexHealerProtocol,
    CodexWorkspaceClient,
    CommitObservation,
    CommitWatcher as _CommitWatcher,
    GitHubClient,
    UpdateResult,
    Updater,
    WorkspaceSubmission,
)

__all__ = [
    "GapInstruction",
    "OracleGapRequest",
    "CodexRelay",
    "NarrativeMark",
    "CommitWatcher",
    "UpdaterLink",
    "ExternalGapResult",
    "ExternalGapSeeker",
]


@dataclass(slots=True, frozen=True)
class GapInstruction:
    """Container describing the Codex task text and optional highlights."""

    text: str
    highlights: tuple[str, ...] = ()


class OracleGapRequest:
    """Compose a natural-language instruction for the Codex workspace."""

    DEFAULT_PROMPT = (
        "Audit the SentientOS repository for TODO/FIXME markers, "
        "unimplemented stubs, missing or weak tests, mypy/type errors, and "
        "coverage holes. Patch the identified gaps directly and ensure CI "
        "passes. Provide a short summary of the fixes applied."
    )

    def __init__(self, *, base_prompt: str | None = None) -> None:
        self._base_prompt = base_prompt.strip() if base_prompt else self.DEFAULT_PROMPT

    def compose(self, *, local_findings: Sequence[GapResolution] | None = None) -> GapInstruction:
        """Return the Codex instruction enriched with known local findings."""

        highlights = tuple(self._summarise_findings(local_findings or ()))
        if not highlights:
            return GapInstruction(text=self._base_prompt)

        context_lines = "\n".join(f"- {item}" for item in highlights)
        prompt = (
            f"{self._base_prompt}\n\nKnown local findings (do not regress):\n"
            f"{context_lines}\n\nPrioritise closing these while auditing the rest of the repo."
        )
        return GapInstruction(text=prompt, highlights=highlights)

    @staticmethod
    def _summarise_findings(findings: Iterable[GapResolution]) -> list[str]:
        summaries: list[str] = []
        for finding in findings:
            gap = finding.gap
            path = getattr(gap, "path", None)
            location = path.name if isinstance(path, Path) else str(path)
            line = getattr(gap, "line", None)
            description = getattr(gap, "description", "").strip() or gap.kind
            summary = f"{gap.kind} at {location}:{line} — {description}".strip()
            summaries.append(summary)
        return summaries


class NarrativeMark:
    """Record external gap-seek lineage entries in the :class:`RecoveryLedger`."""

    AUTHOR = "codex.external_gap_seeker"

    def __init__(
        self,
        ledger: RecoveryLedger,
        *,
        on_record: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self._ledger = ledger
        self._records: list[dict[str, object]] = []
        self._on_record = on_record

    def record_request(
        self,
        submission: WorkspaceSubmission,
        instruction: GapInstruction,
        *,
        metadata: Mapping[str, object] | None = None,
        attachments: Sequence[Path] = (),
    ) -> None:
        details: dict[str, object] = {
            "task_id": submission.task_id,
            "commit_sha": submission.commit_sha,
            "author": self.AUTHOR,
        }
        if submission.pr_url:
            details["pr_url"] = submission.pr_url
        if instruction.highlights:
            details["highlights"] = list(instruction.highlights)
        if attachments:
            details["attachments"] = [str(path) for path in attachments]
        if metadata:
            details["metadata"] = dict(metadata)
        anomaly = Anomaly(
            "external_gap_seek_request",
            submission.task_id,
            {"instruction": instruction.text},
        )
        entry = self._ledger.log("external_gap_seek_requested", anomaly=anomaly, details=details)
        self._records.append({"status": "external_gap_seek_requested", "entry": entry})
        if self._on_record:
            self._on_record(self._records[-1])

    def record_commit(self, observation: CommitObservation) -> None:
        details: dict[str, object] = {
            "commit_sha": observation.commit_sha,
            "status": observation.status,
            "ci_passed": observation.ci_passed,
            "merged": observation.merged,
            "details": dict(observation.details),
            "author": self.AUTHOR,
        }
        quarantined = observation.status != "success" or not observation.ci_passed or not observation.merged
        anomaly = Anomaly(
            "external_gap_seek_commit",
            observation.commit_sha,
            {"status": observation.status},
        )
        entry = self._ledger.log(
            "external_gap_seek_commit",
            anomaly=anomaly,
            details=details,
            quarantined=quarantined,
        )
        self._records.append(
            {
                "status": "external_gap_seek_commit",
                "entry": entry,
                "quarantined": quarantined,
            }
        )
        if self._on_record:
            self._on_record(self._records[-1])

    def record_update(self, result: UpdateResult) -> None:
        details = {
            "commit_sha": result.commit_sha,
            "pulled": result.pulled,
            "reloaded": result.reloaded,
            "author": self.AUTHOR,
        }
        status = "external_gap_seek_applied" if result.pulled else "external_gap_seek_update_failed"
        anomaly = Anomaly("external_gap_seek_update", result.commit_sha, {})
        entry = self._ledger.log(status, anomaly=anomaly, details=details, quarantined=not result.pulled)
        self._records.append({"status": status, "entry": entry, "quarantined": not result.pulled})
        if self._on_record:
            self._on_record(self._records[-1])

    def summary(self) -> str:
        if not self._records:
            return "No external gap-seek consults recorded."
        requests = sum(1 for record in self._records if record["status"] == "external_gap_seek_requested")
        merged = sum(
            1
            for record in self._records
            if record["status"] == "external_gap_seek_commit" and not record.get("quarantined", False)
        )
        pending = sum(
            1
            for record in self._records
            if record["status"] == "external_gap_seek_commit" and record.get("quarantined", False)
        )
        updates = sum(
            1
            for record in self._records
            if record["status"] == "external_gap_seek_applied" and not record.get("quarantined", False)
        )
        summary = (
            f"External gap-seek consult by {self.AUTHOR}: "
            f"{requests} request(s), {merged} merged commit(s), {updates} update(s) applied."
        )
        if pending:
            summary += f" {pending} observation(s) require follow-up."
        return summary


class CodexRelay:
    """Submit the gap instruction to the Codex workspace and log lineage."""

    def __init__(
        self,
        workspace: CodexWorkspaceClient,
        *,
        narrative: NarrativeMark | None = None,
    ) -> None:
        self._workspace = workspace
        self._narrative = narrative

    def dispatch(
        self,
        instruction: GapInstruction,
        *,
        attachments: Sequence[Path] = (),
        metadata: Mapping[str, object] | None = None,
    ) -> WorkspaceSubmission:
        normalised = tuple(Path(path) for path in attachments)
        submission = self._workspace.submit(instruction.text, attachments=normalised)
        if self._narrative is not None:
            extra = dict(metadata or {})
            if instruction.highlights and "highlights" not in extra:
                extra["highlights"] = list(instruction.highlights)
            self._narrative.record_request(
                submission,
                instruction,
                metadata=extra or None,
                attachments=normalised,
            )
        return submission


class CommitWatcher:
    """Wrapper around :class:`sentientos.oracle_cycle.CommitWatcher` with narration."""

    def __init__(
        self,
        github: GitHubClient,
        ledger: RecoveryLedger,
        *,
        healer: CodexHealerProtocol | None = None,
        narrative: NarrativeMark | None = None,
    ) -> None:
        self._delegate = _CommitWatcher(github, ledger, healer=healer)
        self._narrative = narrative

    def await_commit(self, commit_sha: str, *, timeout: float | None = None) -> CommitObservation:
        observation = self._delegate.await_commit(commit_sha, timeout=timeout)
        if self._narrative is not None:
            self._narrative.record_commit(observation)
        return observation


class UpdaterLink:
    """Bridge that applies merged commits locally and records lineage."""

    def __init__(self, updater: Updater, *, narrative: NarrativeMark | None = None) -> None:
        self._updater = updater
        self._narrative = narrative

    def apply(self, commit_sha: str) -> UpdateResult:
        result = self._updater.apply(commit_sha)
        if self._narrative is not None:
            self._narrative.record_update(result)
        return result


@dataclass(slots=True)
class ExternalGapResult:
    """Outcome returned by :class:`ExternalGapSeeker`."""

    instruction: GapInstruction
    submission: WorkspaceSubmission
    observation: CommitObservation
    update_result: UpdateResult | None


class ExternalGapSeeker:
    """Coordinate the ExternalGapSeeker workflow end-to-end."""

    def __init__(
        self,
        request: OracleGapRequest,
        relay: CodexRelay,
        watcher: CommitWatcher,
        updater: UpdaterLink,
    ) -> None:
        self._request = request
        self._relay = relay
        self._watcher = watcher
        self._updater = updater

    def run(
        self,
        *,
        local_findings: Sequence[GapResolution] | None = None,
        timeout: float | None = None,
    ) -> ExternalGapResult:
        instruction = self._request.compose(local_findings=local_findings)
        metadata: MutableMapping[str, object] = {
            "local_findings_count": len(local_findings or ()),
        }
        if local_findings:
            metadata["local_findings_paths"] = [str(item.gap.path) for item in local_findings]
        submission = self._relay.dispatch(instruction, metadata=metadata)
        observation = self._watcher.await_commit(submission.commit_sha, timeout=timeout)
        update_result: UpdateResult | None = None
        if observation.status == "success" and observation.ci_passed and observation.merged:
            update_result = self._updater.apply(observation.commit_sha)
        return ExternalGapResult(
            instruction=instruction,
            submission=submission,
            observation=observation,
            update_result=update_result,
        )
