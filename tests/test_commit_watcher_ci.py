from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Callable, Mapping, Sequence

import pytest

from sentientos.codex_healer import Anomaly, RecoveryLedger, RepairAction
from sentientos.oracle_cycle import (
    BackoffPolicy,
    CIChecker,
    CheckRun,
    CommitObservation,
    CommitWatcher,
    FailureHandler,
    MergeDecision,
    MergeGate,
    NarratorLink,
    PRMonitor,
    PullRequestInfo,
)


class RecordingGitHubClient:
    def __init__(self, observation: CommitObservation) -> None:
        self._observation = observation
        self.queries: list[str] = []

    def wait_for_commit(self, commit_sha: str, *, timeout: float | None = None) -> CommitObservation:
        self.queries.append(commit_sha)
        return self._observation


class RecordingHealer:
    def __init__(self) -> None:
        self.invocations: list[tuple[Anomaly, RepairAction]] = []

    def review_external(self, anomaly: Anomaly, action: RepairAction) -> Mapping[str, object]:
        self.invocations.append((anomaly, action))
        return {"status": "queued"}


class FakePRProvider:
    def __init__(self, pull_requests: Sequence[PullRequestInfo]) -> None:
        self._pull_requests = list(pull_requests)
        self.requests = 0

    def list_pull_requests(self) -> Sequence[PullRequestInfo]:
        self.requests += 1
        return list(self._pull_requests)


class SequencedCheckProvider:
    def __init__(self, sequences: Sequence[Sequence[CheckRun]]) -> None:
        self._sequences: deque[Sequence[CheckRun]] = deque(sequences)
        self.requests: list[int] = []

    def list_check_runs(self, pull_request: PullRequestInfo) -> Sequence[CheckRun]:
        self.requests.append(pull_request.number)
        if not self._sequences:
            return []
        return list(self._sequences.popleft())


class RecordingMergeStrategy:
    def __init__(self, *, succeed: bool = True) -> None:
        self.succeed = succeed
        self.calls: list[int] = []

    def __call__(self, pull_request: PullRequestInfo) -> MergeDecision:
        self.calls.append(pull_request.number)
        if not self.succeed:
            return MergeDecision(merged=False, reason="merge_strategy_declined")
        return MergeDecision(merged=True, sha=pull_request.head_sha, message="merged")


def _now() -> datetime:
    return datetime(2024, 1, 1, tzinfo=timezone.utc)


def _commit_observation(*, merged: bool, ci_passed: bool = True) -> CommitObservation:
    return CommitObservation(
        commit_sha="abc123",
        status="success" if ci_passed else "failure",
        ci_passed=ci_passed,
        merged=merged,
        timestamp=_now(),
        details={},
    )


def _success_check(name: str = "ci") -> CheckRun:
    return CheckRun(name=name, status="completed", conclusion="success")


def _failure_check(name: str = "ci") -> CheckRun:
    return CheckRun(name=name, status="completed", conclusion="failure")


def _pending_check(name: str = "ci") -> CheckRun:
    return CheckRun(name=name, status="in_progress", conclusion=None)


def _make_pr(head_sha: str = "abc123", *, author: str = "SentientOS", base: str = "main") -> PullRequestInfo:
    return PullRequestInfo(
        number=42,
        title="Automated fix",
        author=author,
        head_sha=head_sha,
        base_ref=base,
        url="https://example.test/pr/42",
        mergeable=True,
    )


def test_commit_watcher_auto_merges_green_ci(tmp_path) -> None:
    ledger = RecoveryLedger(tmp_path / "ledger.jsonl")
    pull_request = _make_pr()
    provider = FakePRProvider([pull_request])
    check_provider = SequencedCheckProvider([[ _success_check("build"), _success_check("tests") ]])
    monitor = PRMonitor(provider)
    checker = CIChecker(check_provider)
    merge_strategy = RecordingMergeStrategy()
    gate = MergeGate(merge_strategy)
    announcements: list[tuple[str, Mapping[str, object]]] = []

    def _announce(message: str, payload: Mapping[str, object]) -> None:
        announcements.append((message, payload))

    narrator = NarratorLink(on_announce=_announce)
    failure_handler = FailureHandler(ledger, narrator=narrator)
    observation = _commit_observation(merged=False)
    github = RecordingGitHubClient(observation)
    watcher = CommitWatcher(
        github,
        ledger,
        pr_monitor=monitor,
        ci_checker=checker,
        merge_gate=gate,
        failure_handler=failure_handler,
        narrator=narrator,
        sleep=lambda _: None,
    )

    result = watcher.await_commit(observation.commit_sha)

    assert result.merged is True
    assert result.details["auto_merge"]["status"] == "merged"
    statuses = [entry["status"] for entry in ledger.entries]
    assert "pr_auto_merged" in statuses
    assert "commit_merged" in statuses
    assert merge_strategy.calls == [pull_request.number]
    assert announcements and announcements[0][0].startswith("A self-amendment was merged")


def test_commit_watcher_handles_failing_ci(tmp_path) -> None:
    ledger = RecoveryLedger(tmp_path / "ledger.jsonl")
    healer = RecordingHealer()
    pull_request = _make_pr()
    provider = FakePRProvider([pull_request])
    check_provider = SequencedCheckProvider([[ _failure_check("tests") ]])
    monitor = PRMonitor(provider)
    checker = CIChecker(check_provider)
    merge_strategy = RecordingMergeStrategy()
    gate = MergeGate(merge_strategy)
    narrator = NarratorLink()
    failure_handler = FailureHandler(ledger, healer=healer, narrator=narrator)
    observation = _commit_observation(merged=False)
    github = RecordingGitHubClient(observation)
    watcher = CommitWatcher(
        github,
        ledger,
        pr_monitor=monitor,
        ci_checker=checker,
        merge_gate=gate,
        failure_handler=failure_handler,
        narrator=narrator,
        sleep=lambda _: None,
    )

    result = watcher.await_commit(observation.commit_sha)

    assert result.merged is False
    assert result.ci_passed is False
    assert result.details["auto_merge"]["status"] == "ci_failed"
    statuses = [entry["status"] for entry in ledger.entries]
    assert "pr_ci_failed" in statuses
    assert "commit_failed" in statuses
    assert healer.invocations, "CodexHealer should be invoked for CI failures"
    assert narrator.history and narrator.history[-1]["event"] == "failure"


def test_commit_watcher_retries_pending_ci_with_backoff(tmp_path) -> None:
    ledger = RecoveryLedger(tmp_path / "ledger.jsonl")
    pull_request = _make_pr()
    provider = FakePRProvider([pull_request])
    check_provider = SequencedCheckProvider([
        [_pending_check("build")],
        [_pending_check("tests")],
        [_success_check("build"), _success_check("tests")],
    ])
    monitor = PRMonitor(provider)
    checker = CIChecker(check_provider)
    merge_strategy = RecordingMergeStrategy()
    gate = MergeGate(merge_strategy)
    narrator = NarratorLink()
    failure_handler = FailureHandler(ledger, narrator=narrator)
    observation = _commit_observation(merged=False)
    github = RecordingGitHubClient(observation)
    sleep_calls: list[float] = []

    def _sleep(duration: float) -> None:
        sleep_calls.append(duration)

    watcher = CommitWatcher(
        github,
        ledger,
        pr_monitor=monitor,
        ci_checker=checker,
        merge_gate=gate,
        failure_handler=failure_handler,
        narrator=narrator,
        backoff=BackoffPolicy(initial_seconds=1.0, multiplier=2.0, max_seconds=8.0),
        sleep=_sleep,
        max_ci_attempts=5,
    )

    result = watcher.await_commit(observation.commit_sha)

    assert result.merged is True
    assert sleep_calls == [1.0, 2.0]
    assert result.details["auto_merge"]["attempts"] == 3


def test_commit_watcher_ignores_manual_prs(tmp_path) -> None:
    ledger = RecoveryLedger(tmp_path / "ledger.jsonl")
    manual_pr = _make_pr(author="Operator", head_sha="abc123")
    provider = FakePRProvider([manual_pr])
    monitor = PRMonitor(provider)
    checker = CIChecker(SequencedCheckProvider([]))
    merge_strategy = RecordingMergeStrategy()
    gate = MergeGate(merge_strategy)
    narrator = NarratorLink()
    failure_handler = FailureHandler(ledger, narrator=narrator)
    observation = _commit_observation(merged=False)
    github = RecordingGitHubClient(observation)

    watcher = CommitWatcher(
        github,
        ledger,
        pr_monitor=monitor,
        ci_checker=checker,
        merge_gate=gate,
        failure_handler=failure_handler,
        narrator=narrator,
        sleep=lambda _: None,
    )

    result = watcher.await_commit(observation.commit_sha)

    auto_details = result.details.get("auto_merge")
    assert auto_details["status"] == "skipped"
    assert auto_details["reason"] == "no_matching_pr"
    assert not merge_strategy.calls
    statuses = [entry["status"] for entry in ledger.entries]
    assert "pr_auto_merged" not in statuses
    assert "pr_ci_failed" not in statuses

