from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import subprocess

import pytest

from sentientos.research_timer import (
    CommitPublisher,
    DeepResearchService,
    HistoryCollector,
    NarratorLink,
    OracleConsult,
    ReportWriter,
    TimerDaemon,
)


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    lines = [json.dumps(record) for record in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_timer_daemon_interval(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    timer = TimerDaemon(state, interval_days=2, clock=lambda: datetime(2024, 1, 3, tzinfo=UTC))
    assert timer.should_run()
    timer.mark_ran(datetime(2024, 1, 1, tzinfo=UTC))
    assert not timer.should_run(datetime(2024, 1, 2, tzinfo=UTC))
    assert timer.should_run(datetime(2024, 1, 3, tzinfo=UTC))
    assert timer.time_until_next(datetime(2024, 1, 3, tzinfo=UTC)) == timedelta(0)


def test_history_collector_collects_commits_and_events(tmp_path: Path) -> None:
    repo = tmp_path
    _init_repo(repo)
    (repo / "sample.txt").write_text("initial", encoding="utf-8")
    subprocess.run(["git", "add", "sample.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True)

    since = datetime.now(UTC) - timedelta(days=1)
    (repo / "ledger.jsonl").write_text("", encoding="utf-8")
    (repo / "narration.jsonl").write_text("", encoding="utf-8")

    (repo / "later.txt").write_text("later", encoding="utf-8")
    subprocess.run(["git", "add", "later.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "later"], cwd=repo, check=True)

    now = datetime.now(UTC)
    _write_jsonl(
        repo / "ledger.jsonl",
        [{"timestamp": now.isoformat(), "event": "ledger"}],
    )
    _write_jsonl(
        repo / "narration.jsonl",
        [{"timestamp": now.isoformat(), "event": "narration"}],
    )

    collector = HistoryCollector(
        repo,
        ledger_sources=[Path("ledger.jsonl")],
        narration_sources=[Path("narration.jsonl")],
    )
    window = collector.collect(since, now)
    assert window.commits, "should capture new commits"
    assert window.ledger_entries and window.ledger_entries[0].payload["event"] == "ledger"
    assert window.narration_events and window.narration_events[0].payload["event"] == "narration"


def test_oracle_consult_uses_callable(tmp_path: Path) -> None:
    repo = tmp_path
    _init_repo(repo)
    collector = HistoryCollector(repo)
    now = datetime.now(UTC)
    window = collector.collect(now - timedelta(days=1), now)
    recorded_prompt: list[str] = []

    def fake_oracle(prompt: str) -> str:
        recorded_prompt.append(prompt)
        return "Summary"

    oracle = OracleConsult(fake_oracle)
    result = oracle.consult(window)
    assert result == "Summary"
    assert "Summarize SentientOS GitHub progress" in recorded_prompt[0]


def test_report_writer_outputs_expected_markdown(tmp_path: Path) -> None:
    writer = ReportWriter(tmp_path)
    now = datetime(2024, 5, 1, tzinfo=UTC)
    window = HistoryCollector(tmp_path).collect(now - timedelta(days=1), now)
    summary = "A summary"
    path = writer.write(window, summary)
    assert path.parent.name == "research"
    content = path.read_text(encoding="utf-8")
    assert "# Deep Research Reflection" in content
    assert summary in content


def test_commit_publisher_commits_report(tmp_path: Path) -> None:
    repo = tmp_path
    _init_repo(repo)
    now = datetime.now(UTC)
    window = HistoryCollector(repo).collect(now - timedelta(days=1), now)
    report = repo / "glow" / "research" / "report.md"
    report.parent.mkdir(parents=True)
    report.write_text("content", encoding="utf-8")
    publisher = CommitPublisher(repo)
    result = publisher.publish(window, report, "summary")
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "Deep Research reflection" in log
    assert "[lineage: deep-research]" in log
    assert result.commit_hash


def test_service_runs_full_cycle(tmp_path: Path) -> None:
    repo = tmp_path
    _init_repo(repo)
    (repo / "base.txt").write_text("base", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True)

    ledger_path = repo / "ledger.jsonl"
    narration_path = repo / "narration.jsonl"

    now = datetime(2024, 1, 1, tzinfo=UTC)
    _write_jsonl(
        ledger_path,
        [{"timestamp": (now - timedelta(hours=1)).isoformat(), "event": "ledger"}],
    )
    _write_jsonl(
        narration_path,
        [{"timestamp": (now - timedelta(hours=1)).isoformat(), "event": "narration"}],
    )

    timer = TimerDaemon(repo / "state.json", interval_days=1, clock=lambda: now)
    collector = HistoryCollector(
        repo,
        ledger_sources=[Path("ledger.jsonl")],
        narration_sources=[Path("narration.jsonl")],
    )
    oracle = OracleConsult(lambda prompt: "Oracle summary")
    writer = ReportWriter(repo)
    publisher = CommitPublisher(repo)
    messages: list[str] = []
    narrator = NarratorLink(messages.append)
    service = DeepResearchService(timer, collector, oracle, writer, publisher, narrator)

    first_path = service.run(now)
    assert first_path is not None and first_path.exists()
    assert messages, "narrator should be notified"

    # Second run after interval creates a new report without removing old one
    later = now + timedelta(days=2)
    _write_jsonl(
        ledger_path,
        [{"timestamp": (later - timedelta(hours=1)).isoformat(), "event": "ledger2"}],
    )
    _write_jsonl(
        narration_path,
        [{"timestamp": (later - timedelta(hours=1)).isoformat(), "event": "narration2"}],
    )
    timer.mark_ran(now - timedelta(days=1))  # simulate last run in the past
    second_path = service.run(later)
    assert second_path is not None and second_path.exists()
    assert first_path != second_path
    assert first_path.exists(), "previous report must remain"  # regression guard

