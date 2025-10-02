from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sentientos.change_narrator import ChangeCollector, ChangeNarrator
from sentientos.codex_healer import Anomaly, RecoveryLedger


def _init_repo(path: Path) -> None:
    subprocess.run(("git", "init"), cwd=path, check=True, capture_output=True)
    subprocess.run(("git", "config", "user.name", "Test User"), cwd=path, check=True, capture_output=True)
    subprocess.run(("git", "config", "user.email", "test@example.com"), cwd=path, check=True, capture_output=True)


def _git_timestamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S %z")


def _commit(path: Path, filename: str, content: str, message: str, *, moment: datetime) -> None:
    target = path / filename
    target.write_text(content, encoding="utf-8")
    subprocess.run(("git", "add", filename), cwd=path, check=True, capture_output=True)
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = _git_timestamp(moment)
    env["GIT_COMMITTER_DATE"] = _git_timestamp(moment)
    subprocess.run(("git", "commit", "-m", message), cwd=path, check=True, capture_output=True, env=env)


def test_change_narrator_handles_no_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_root = tmp_path / "data"
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    narrator = ChangeNarrator(ChangeCollector(repo_path=repo))
    reply = narrator.maybe_respond("What changed?")

    assert reply == "No changes since the last update."


def test_change_narrator_summarises_commits_and_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_root = tmp_path / "data"
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    anchor = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)
    _commit(repo, "loader.py", "print('loader')\n", "Add LocalModel loader", moment=anchor - timedelta(hours=2))
    _commit(repo, "fallback.py", "print('fallback')\n", "Add fallback inference", moment=anchor - timedelta(hours=1))

    ledger = RecoveryLedger()
    first_entry = ledger.log("heal_started", anomaly=Anomaly("codex", "loader"))
    first_entry["timestamp"] = (anchor - timedelta(hours=3)).isoformat()
    second_entry = ledger.log("heal_completed", anomaly=Anomaly("codex", "loader"))
    second_entry["timestamp"] = (anchor - timedelta(hours=1, minutes=30)).isoformat()

    narrator = ChangeNarrator(ChangeCollector(ledger=ledger, repo_path=repo))

    reply = narrator.maybe_respond("Can you summarise the latest changes?", now=anchor)

    assert reply is not None
    assert "Add LocalModel loader" in reply
    assert "Add fallback inference" in reply
    assert "heal started" in reply
    assert "heal completed" in reply

    follow_up = narrator.maybe_respond("What changed?", now=anchor + timedelta(minutes=5))
    assert follow_up == "No changes since the last update."


def test_time_filtered_query_respects_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_root = tmp_path / "data"
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    anchor = datetime(2024, 5, 2, 12, 0, tzinfo=timezone.utc)
    old_commit_time = anchor - timedelta(days=3)
    recent_commit_time = anchor - timedelta(hours=4)
    _commit(repo, "history.txt", "old\n", "Legacy refactor", moment=old_commit_time)
    _commit(repo, "status.txt", "new\n", "Patch self-healing", moment=recent_commit_time)

    narrator = ChangeNarrator(ChangeCollector(repo_path=repo))
    reply = narrator.maybe_respond("What changed since yesterday?", now=anchor)

    assert reply is not None
    assert "Patch self-healing" in reply
    assert "Legacy refactor" not in reply


def test_module_filter_does_not_hide_other_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_root = tmp_path / "data"
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    ledger = RecoveryLedger()
    codex_entry = ledger.log("heal_started", anomaly=Anomaly("codex", "core"))
    codex_entry["timestamp"] = datetime(2024, 5, 1, 8, 0, tzinfo=timezone.utc).isoformat()
    oracle_entry = ledger.log("heal_completed", anomaly=Anomaly("oracle", "cycle"))
    oracle_entry["timestamp"] = datetime(2024, 5, 1, 9, 0, tzinfo=timezone.utc).isoformat()

    narrator = ChangeNarrator(ChangeCollector(ledger=ledger, repo_path=repo))

    codex_reply = narrator.maybe_respond("Share Codex changes", now=datetime(2024, 5, 1, 10, 0, tzinfo=timezone.utc))
    assert codex_reply is not None
    assert "heal started" in codex_reply
    assert "heal completed" not in codex_reply

    general_reply = narrator.maybe_respond("What changed?", now=datetime(2024, 5, 1, 11, 0, tzinfo=timezone.utc))
    assert general_reply is not None
    assert "heal completed" in general_reply
