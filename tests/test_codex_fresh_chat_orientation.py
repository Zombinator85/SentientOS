from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from sentientos.codex_fresh_chat_orientation import OrientationError, observe_orientation

pytestmark = pytest.mark.no_legacy_skip


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "AGENTS.md").write_text("tracked\n", encoding="utf-8")
    (repo / "file.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    return repo


def test_orientation_snapshot_reports_exact_checkout_identity_without_modifying_tree(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = _git(repo, "status", "--porcelain=v2", "--untracked-files=all")
    result = observe_orientation(repo)
    assert result["repository"]["head_sha"] == _git(repo, "rev-parse", "HEAD")
    assert result["repository"]["root"] == str(repo.resolve())
    assert result["repository"]["detached_head"] is False
    assert result["worktree"]["clean"] is True
    assert _git(repo, "status", "--porcelain=v2", "--untracked-files=all") == before


def test_orientation_git_invocations_disable_optional_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path)
    calls: list[list[str]] = []
    original_run = subprocess.run

    def recording_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append(command)
        return original_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)
    observe_orientation(repo)

    assert calls
    assert all(command[:2] == ["git", "--no-optional-locks"] for command in calls)


def test_orientation_branch_detection_uses_hardened_git_execution_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repo(tmp_path)
    calls: list[list[str]] = []
    original_run = subprocess.run

    def recording_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append(command)
        return original_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)
    result = observe_orientation(repo)

    assert result["repository"]["branch"]
    branch_calls = [command for command in calls if "--abbrev-ref" in command]
    assert branch_calls == [
        ["git", "--no-optional-locks", "rev-parse", "--abbrev-ref", "HEAD"],
        ["git", "--no-optional-locks", "rev-parse", "--abbrev-ref", "HEAD"],
    ]


def test_orientation_snapshot_preserves_dirty_and_untracked_state(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "staged name.txt").write_text("staged", encoding="utf-8")
    _git(repo, "add", "staged name.txt")
    (repo / "file.txt").write_text("changed\n", encoding="utf-8")
    (repo / "untracked\nname.txt").write_text("new", encoding="utf-8")
    result = observe_orientation(repo)["worktree"]
    assert result["clean"] is False
    assert {item["path"] for item in result["staged"]} == {"staged name.txt"}
    assert {item["path"] for item in result["unstaged"]} == {"file.txt"}
    assert result["untracked"] == ["untracked\nname.txt"]


def test_orientation_snapshot_separates_tracked_from_untracked_agents(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "nested").mkdir()
    (repo / "nested" / "AGENTS.md").write_text("local", encoding="utf-8")
    surfaces = observe_orientation(repo)["instruction_surfaces"]
    assert surfaces["tracked_agents"] == ["AGENTS.md"]
    assert surfaces["untracked_agents_candidates"] == ["nested/AGENTS.md"]


def test_orientation_snapshot_reports_local_observation_without_claiming_hosted_state(tmp_path: Path) -> None:
    result = observe_orientation(_repo(tmp_path))
    assert result["observability"]["scope"] == "local_checkout_only"
    assert "current_hosted_main" in result["observability"]["not_observed"]


def test_orientation_snapshot_grants_no_implementation_runtime_commit_or_publication_authority(tmp_path: Path) -> None:
    result = observe_orientation(_repo(tmp_path))
    assert not any(result["authority"].values())
    assert not any(result["task_state"].values())


def test_orientation_snapshot_detects_unstable_repository_state(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    calls = 0
    from sentientos import codex_fresh_chat_orientation as module

    def changing(cwd: Path, args: tuple[str, ...]) -> bytes:
        nonlocal calls
        calls += 1
        value = module._run_git(cwd, args)
        if args[:2] == ("status", "--porcelain=v2") and calls > 4:
            return value + b"? changed\0"
        return value

    with pytest.raises(OrientationError, match="unstable_repository_observation"):
        observe_orientation(repo, run_git=changing)


def test_orientation_snapshot_fails_closed_outside_git_repository(tmp_path: Path) -> None:
    with pytest.raises(OrientationError, match="git_observation_failed"):
        observe_orientation(tmp_path)


def test_orientation_snapshot_reports_detached_head(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "checkout", "--detach", "-q")
    identity = observe_orientation(repo)["repository"]
    assert identity["branch"] is None
    assert identity["detached_head"] is True
