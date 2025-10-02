from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

import pytest

from codex.integrity_daemon import IntegrityDaemon

from sentientos.codex_healer import Anomaly, RecoveryLedger, RepairAction
from sentientos.oracle_cycle import (
    CodexExecutor,
    CommitObservation,
    CommitWatcher,
    HealthCheck,
    LedgerLink,
    NarratorLink,
    OracleClient,
    OracleCycle,
    OracleQuery,
    ResearchTimer,
    RollbackHandler,
    SnapshotManager,
    UpdateResult,
    WorkspaceSubmission,
    Updater,
)


class RecordingOracleClient(OracleClient):
    def __init__(self, response: str) -> None:
        self.response = response
        self.questions: list[str] = []

    def ask(self, question: str) -> str:
        self.questions.append(question)
        return self.response


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
        return {"status": "captured"}


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


class FakeRepo:
    def __init__(self, head: str) -> None:
        self.head = head
        self.pull_args: list[str] = []
        self.reset_calls: list[str] = []

    def read_head(self) -> str:
        return self.head

    def pull(self, commit_sha: str) -> bool:
        self.pull_args.append(commit_sha)
        self.head = commit_sha
        return True

    def reset(self, commit_sha: str) -> bool:
        self.reset_calls.append(commit_sha)
        self.head = commit_sha
        return True


class RecordingIntegrityDaemon(IntegrityDaemon):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.proposals = 0

    def evaluate(self, proposal: object) -> None:  # type: ignore[override]
        self.proposals += 1
        return super().evaluate(proposal)


@pytest.fixture
def ledger(tmp_path: Path) -> RecoveryLedger:
    return RecoveryLedger(tmp_path / "ledger.jsonl")


def _build_guidance(
    tmp_path: Path,
    ledger: RecoveryLedger,
    response: str = "Ship feature",
) -> tuple[OracleQuery, RecordingOracleClient]:
    integrity = RecordingIntegrityDaemon(tmp_path)
    client = RecordingOracleClient(response)
    oracle = OracleQuery(client, integrity, ledger=ledger)
    return oracle, client


def test_codex_executor_and_commit_watcher(tmp_path: Path, ledger: RecoveryLedger) -> None:
    oracle, client = _build_guidance(tmp_path, ledger)
    workspace = RecordingWorkspaceClient()
    executor = CodexExecutor(workspace, ledger=ledger)
    now = datetime.now(timezone.utc)
    expected_commit = f"{1:040x}"[-40:]
    observation = CommitObservation(
        commit_sha=expected_commit,
        status="success",
        ci_passed=True,
        merged=True,
        timestamp=now,
        details={"ci": "passed"},
    )
    github = RecordingGitHubClient(observation)
    watcher = CommitWatcher(github, ledger)
    pull = RecordingPull()
    reload = RecordingReload()
    updater = Updater(pull, reload_strategy=reload)
    research_timer = ResearchTimer(
        oracle,
        executor,
        ledger,
        glow_root=tmp_path / "glow",
        period_days=30,
        state_path=tmp_path / "state.json",
    )
    cycle = OracleCycle(oracle, executor, watcher, updater, research_timer)

    result = cycle.run_once()

    assert client.questions[0].startswith("What step should I take next")
    assert workspace.instructions, "CodexExecutor should submit an instruction"
    assert result.execution.commit_sha == expected_commit
    assert github.queries == [result.execution.commit_sha]
    assert result.observation.status == "success"
    assert pull.arguments == [observation.commit_sha]
    assert reload.invocations == 1
    assert result.update_result == UpdateResult(observation.commit_sha, True, True)
    entries = ledger.entries
    assert any(entry["status"] == "commit_merged" for entry in entries)


def test_commit_watcher_invokes_healer_on_failure(tmp_path: Path, ledger: RecoveryLedger) -> None:
    oracle, _ = _build_guidance(tmp_path, ledger)
    workspace = RecordingWorkspaceClient()
    executor = CodexExecutor(workspace, ledger=ledger)
    now = datetime.now(timezone.utc)
    observation = CommitObservation(
        commit_sha="e" * 40,
        status="failure",
        ci_passed=False,
        merged=False,
        timestamp=now,
        details={"ci": "failed"},
    )
    github = RecordingGitHubClient(observation)
    healer = RecordingHealer()
    watcher = CommitWatcher(github, ledger, healer=healer)

    watcher.await_commit(observation.commit_sha)

    assert healer.invocations, "CodexHealer should intervene on CI failure"
    assert ledger.entries[-1]["status"] == "commit_failed"


def test_research_timer_runs_on_schedule(tmp_path: Path, ledger: RecoveryLedger) -> None:
    oracle, client = _build_guidance(tmp_path, ledger, response="Progress summary")
    workspace = RecordingWorkspaceClient()
    executor = CodexExecutor(workspace, ledger=ledger)
    research_timer = ResearchTimer(
        oracle,
        executor,
        ledger,
        glow_root=tmp_path / "glow",
        period_days=1,
        state_path=tmp_path / "research_state.json",
    )
    now = datetime.now(timezone.utc)
    observation = CommitObservation(
        commit_sha="d" * 40,
        status="success",
        ci_passed=True,
        merged=True,
        timestamp=now,
        details={},
    )

    assert research_timer.record_commit(observation, now=now) is None
    later = now + timedelta(days=1, minutes=1)
    report = research_timer.record_commit(observation, now=later)

    assert report is not None
    assert report.path.exists()
    saved = report.path.read_text(encoding="utf-8")
    assert "Deep Research Report" in saved
    assert workspace.instructions[-1][0].startswith("Commit the latest deep research report")
    assert client.questions[-1].startswith("Summarize SentientOS GitHub progress")
    assert ledger.entries[-1]["status"] == "deep_research_recorded"


def test_updater_records_successful_update(tmp_path: Path, ledger: RecoveryLedger) -> None:
    repo = FakeRepo("a" * 40)
    snapshot_path = tmp_path / "state" / "last_good"
    snapshot = SnapshotManager(read_current=repo.read_head, storage_path=snapshot_path)
    health = HealthCheck({"IntegrityDaemon": lambda: True})
    updater = Updater(
        repo.pull,
        reload_strategy=lambda: True,
        snapshot_manager=snapshot,
        health_check=health,
        ledger=LedgerLink(ledger),
    )

    new_commit = "b" * 40
    result = updater.apply(new_commit)

    assert repo.head == new_commit
    assert result.commit_sha == new_commit
    assert result.last_known_good == new_commit
    assert result.ledger_entry is not None
    assert result.ledger_entry["status"] == "Update applied"
    assert result.health_report is not None and result.health_report.healthy
    assert snapshot_path.read_text(encoding="utf-8").strip() == new_commit


def test_updater_rolls_back_on_failed_health(tmp_path: Path, ledger: RecoveryLedger) -> None:
    repo = FakeRepo("c" * 40)
    snapshot = SnapshotManager(
        read_current=repo.read_head,
        storage_path=tmp_path / "state" / "rollback_last_good",
    )
    events: list[dict[str, object]] = []
    narrator = NarratorLink(
        on_announce=lambda message, payload: events.append({"message": message, **payload})
    )
    health = HealthCheck(
        {"IntegrityDaemon": lambda: False},
        timeout=0.0,
        interval=0.0,
        sleep=lambda _: None,
    )
    rollback = RollbackHandler(repo.reset)
    updater = Updater(
        repo.pull,
        reload_strategy=lambda: True,
        snapshot_manager=snapshot,
        health_check=health,
        rollback_handler=rollback,
        ledger=LedgerLink(ledger),
        narrator=narrator,
    )

    failed_commit = "d" * 40
    result = updater.apply(failed_commit)

    assert result.failure_reason == "health_check_failed"
    assert result.rolled_back
    assert result.rollback_commit == "c" * 40
    assert repo.head == "c" * 40
    assert ledger.entries[-1]["status"] == "Rolled back to last stable commit"
    assert events, "Narrator should announce the rollback"
    assert "restored commit" in events[-1]["message"]


def test_updater_logs_missing_snapshot(tmp_path: Path, ledger: RecoveryLedger) -> None:
    repo = FakeRepo("e" * 40)

    def read_missing() -> str | None:
        return None

    snapshot = SnapshotManager(
        read_current=read_missing,
        storage_path=tmp_path / "state" / "missing_last_good",
    )
    events: list[dict[str, object]] = []
    narrator = NarratorLink(
        on_announce=lambda message, payload: events.append({"message": message, **payload})
    )
    health = HealthCheck(
        {"IntegrityDaemon": lambda: False},
        timeout=0.0,
        interval=0.0,
        sleep=lambda _: None,
    )
    rollback = RollbackHandler(repo.reset)
    updater = Updater(
        repo.pull,
        reload_strategy=lambda: True,
        snapshot_manager=snapshot,
        health_check=health,
        rollback_handler=rollback,
        ledger=LedgerLink(ledger),
        narrator=narrator,
    )

    result = updater.apply("f" * 40)

    assert result.failure_reason == "health_check_failed"
    assert not result.rolled_back
    assert result.ledger_entry is not None
    assert result.ledger_entry["status"] == "Rollback snapshot missing"
    assert events and events[-1]["restored_commit"] is None


def test_oracle_query_remains_integrity_gated(tmp_path: Path, ledger: RecoveryLedger) -> None:
    oracle, client = _build_guidance(tmp_path, ledger)
    guidance = oracle.consult()
    assert guidance.instruction == client.response
    assert client.questions, "OracleQuery must ask the oracle"
    assert oracle._integrity.proposals == 1  # type: ignore[attr-defined]
