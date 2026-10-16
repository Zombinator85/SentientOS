from __future__ import annotations

from types import SimpleNamespace

import pytest

import sentientos.runtime.startup as startup


def observation(pid: int = 4312, status: str = "running_observed") -> dict[str, object]:
    return {"process_id": pid, "runtime_status": status}


def test_prior_child_presence_blocks_new_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(startup.os, "name", "posix")
    monkeypatch.setattr(startup.os, "kill", lambda pid, signal: None)
    with pytest.raises(RuntimeError, match="chat_runtime_prior_child_may_be_running"):
        startup._require_prior_chat_child_absent(observation())


def test_prior_child_pid_absence_allows_new_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    def absent(pid: int, signal: int) -> None:
        raise ProcessLookupError(pid)
    monkeypatch.setattr(startup.os, "name", "posix")
    monkeypatch.setattr(startup.os, "kill", absent)
    startup._require_prior_chat_child_absent(observation(status="not_verified"))


def test_unobservable_prior_child_blocks_new_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(startup.os, "name", "nt")
    with pytest.raises(RuntimeError, match="chat_runtime_prior_child_presence_unavailable"):
        startup._require_prior_chat_child_absent(observation())


def test_invalid_prior_child_identity_blocks_new_launch() -> None:
    with pytest.raises(RuntimeError, match="chat_runtime_prior_child_identity_invalid"):
        startup._require_prior_chat_child_absent({"process_id": True})


def test_missing_prior_observation_preserves_fresh_start() -> None:
    startup._require_prior_chat_child_absent(None)
