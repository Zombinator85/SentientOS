from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

import pytest

from codex.gap_seeker import GapResolution, GapSignal
from sentientos.codex_healer import Anomaly, RecoveryLedger, RepairAction
from sentientos.external_gap_seeker import (
    CodexRelay,
    CommitWatcher,
    ExternalGapSeeker,
    NarrativeMark,
    OracleGapRequest,
    UpdaterLink,
)
from sentientos.oracle_cycle import CommitObservation, UpdateResult, Updater, WorkspaceSubmission


class RecordingWorkspaceClient:
    def __init__(self) -> None:
        self.instructions: list[tuple[str, tuple[Path, ...]]] = []
        self._counter = 0

    def submit(self, instruction: str, *, attachments: Sequence[Path] = ()) -> WorkspaceSubmission:
        self._counter += 1
        commit_sha = f"{self._counter:040x}"[-40:]
        paths = tuple(Path(path) for path in attachments)
        self.instructions.append((instruction, paths))
        return WorkspaceSubmission(task_id=f"task-{self._counter}", commit_sha=commit_sha)


class RecordingGitHubClient:
    def __init__(self, observation: CommitObservation) -> None:
        self.observation = observation
        self.queries: list[str] = []

    def wait_for_commit(self, commit_sha: str, *, timeout: float | None = None) -> CommitObservation:
        self.queries.append(commit_sha)
        return self.observation


class RecordingHealer:
    def __init__(self) -> None:
        self.invocations: list[tuple[Anomaly, RepairAction]] = []

    def review_external(self, anomaly: Anomaly, action: RepairAction) -> Mapping[str, object]:
        self.invocations.append((anomaly, action))
        return {"status": "queued"}


class RecordingPull:
    def __init__(self, succeed: bool = True) -> None:
        self.succeed = succeed
        self.arguments: list[str] = []

    def __call__(self, commit_sha: str) -> bool:
        self.arguments.append(commit_sha)
        return self.succeed


class RecordingReload:
    def __init__(self, succeed: bool = True) -> None:
        self.succeed = succeed
        self.invocations = 0

    def __call__(self) -> bool:
        self.invocations += 1
        return self.succeed


@pytest.fixture
def ledger(tmp_path: Path) -> RecoveryLedger:
    return RecoveryLedger(tmp_path / "ledger.jsonl")


def _make_gap(tmp_path: Path) -> GapResolution:
    signal = GapSignal(
        path=tmp_path / "module.py",
        line=12,
        description="TODO: tighten guard rails",
        severity="medium",
        kind="todo",
        source="repo",
    )
    return GapResolution(gap=signal, action="spec", status="amendment", payload={})


def test_external_gap_seeker_success(tmp_path: Path, ledger: RecoveryLedger) -> None:
    gap = _make_gap(tmp_path)
    request = OracleGapRequest()
    narrative_events: list[dict[str, object]] = []
    narrative = NarrativeMark(ledger, on_record=narrative_events.append)
    workspace = RecordingWorkspaceClient()
    relay = CodexRelay(workspace, narrative=narrative)
    now = datetime.now(timezone.utc)
    observation = CommitObservation(
        commit_sha="a" * 40,
        status="success",
        ci_passed=True,
        merged=True,
        timestamp=now,
        details={"ci": "passed"},
    )
    github = RecordingGitHubClient(observation)
    watcher = CommitWatcher(github, ledger, narrative=narrative)
    pull = RecordingPull()
    reload = RecordingReload()
    updater = Updater(pull, reload_strategy=reload)
    updater_link = UpdaterLink(updater, narrative=narrative)
    seeker = ExternalGapSeeker(request, relay, watcher, updater_link)

    snapshot = (gap,)
    result = seeker.run(local_findings=snapshot)

    assert workspace.instructions, "CodexRelay should submit an instruction"
    submitted_text, _ = workspace.instructions[0]
    assert "Audit the SentientOS repository" in submitted_text
    assert "Known local findings" in submitted_text
    assert github.queries == [result.submission.commit_sha]
    assert result.update_result == UpdateResult(observation.commit_sha, True, True)
    assert pull.arguments == [observation.commit_sha]
    assert reload.invocations == 1
    assert ledger.entries, "NarrativeMark should append ledger entries"
    external_entries = [entry for entry in ledger.entries if entry["status"].startswith("external_gap_seek")]
    assert all(entry["details"].get("author") == NarrativeMark.AUTHOR for entry in external_entries)
    assert "codex.external_gap_seeker" in narrative.summary()
    assert snapshot == (gap,), "Local gap findings must remain unchanged"


def test_external_gap_seeker_handles_ci_failure(tmp_path: Path, ledger: RecoveryLedger) -> None:
    gap = _make_gap(tmp_path)
    request = OracleGapRequest()
    narrative = NarrativeMark(ledger)
    workspace = RecordingWorkspaceClient()
    relay = CodexRelay(workspace, narrative=narrative)
    now = datetime.now(timezone.utc)
    observation = CommitObservation(
        commit_sha="b" * 40,
        status="failure",
        ci_passed=False,
        merged=False,
        timestamp=now,
        details={"ci": "failed"},
    )
    github = RecordingGitHubClient(observation)
    healer = RecordingHealer()
    watcher = CommitWatcher(github, ledger, healer=healer, narrative=narrative)
    pull = RecordingPull()
    updater = Updater(pull)
    updater_link = UpdaterLink(updater, narrative=narrative)
    seeker = ExternalGapSeeker(request, relay, watcher, updater_link)

    result = seeker.run(local_findings=(gap,))

    assert result.update_result is None, "UpdaterLink should not run on failed commits"
    assert healer.invocations, "CodexHealer should be notified of CI failures"
    summary = narrative.summary()
    assert "follow-up" in summary
    quarantined_entries = [entry for entry in ledger.entries if entry.get("quarantined")]
    assert quarantined_entries, "Failures should be quarantined in the ledger"


def test_oracle_gap_request_highlights_findings(tmp_path: Path) -> None:
    gap = _make_gap(tmp_path)
    request = OracleGapRequest()
    instruction = request.compose(local_findings=(gap,))

    assert gap.gap.description.split(":", 1)[-1].strip() in instruction.text
    assert instruction.highlights
    assert "Known local findings" in instruction.text
