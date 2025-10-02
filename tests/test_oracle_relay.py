"""Unit tests for the OracleRelay browser automation bridge."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sentientos.oracle_relay import (
    ErrorHandler,
    OracleRelay,
    OracleRelayResult,
    OracleTask,
    RelayDriver,
    ResponseScraper,
    SessionExpiredError,
    SessionManager,
    TaskRouter,
    Workspace,
)


@dataclass
class FakeSession:
    workspace: Workspace
    response_payload: Mapping[str, Any]
    cookies_to_export: Sequence[Mapping[str, Any]]
    visited_urls: list[str]
    submitted_prompts: list[str]
    restored: list[Mapping[str, Any]]
    ready_calls: int = 0
    submissions: int = 0

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - interface requirement
        return None

    # BrowserSession API ---------------------------------------------------------
    def restore_cookies(self, cookies: Sequence[Mapping[str, Any]]) -> None:
        self.restored.extend(dict(cookie) for cookie in cookies)

    def export_cookies(self) -> Sequence[Mapping[str, Any]]:
        return self.cookies_to_export

    def goto(self, url: str) -> None:
        self.visited_urls.append(url)

    def ensure_ready(self) -> None:
        self.ready_calls += 1

    def submit(self, prompt: str, attachments: Sequence[Path] = ()) -> None:
        self.submitted_prompts.append(prompt)
        self.submissions += 1

    def wait_for_response(self, *, timeout: float | None = None) -> Mapping[str, Any] | str:
        return self.response_payload


class FakeFactory:
    def __init__(self, session: FakeSession):
        self._session = session
        self.calls: list[Workspace] = []

    def __call__(self, workspace: Workspace) -> FakeSession:
        assert workspace == self._session.workspace
        self.calls.append(workspace)
        return self._session


def build_relay(tmp_path: Path, session: FakeSession, *, router: TaskRouter | None = None, error_handler: ErrorHandler | None = None) -> OracleRelay:
    storage = tmp_path / "cookies.json"
    manager = SessionManager(storage)
    driver = RelayDriver(FakeFactory(session))
    scraper = ResponseScraper(timeout=2.0, poll_interval=0.01)
    handler = error_handler or ErrorHandler(manager, max_retries=1)
    return OracleRelay(session_manager=manager, driver=driver, scraper=scraper, router=router, error_handler=handler)


def test_session_manager_persists_cookies(tmp_path: Path) -> None:
    storage = tmp_path / "cookies.json"
    manager = SessionManager(storage)
    cookies = [{"name": "session", "value": "abc"}]
    manager.save(Workspace.ORACLE, cookies)
    assert storage.exists()
    loaded = manager.load(Workspace.ORACLE)
    assert tuple(cookies) == loaded


def test_relay_driver_smoke_loads_chatgpt(tmp_path: Path) -> None:
    session = FakeSession(
        workspace=Workspace.ORACLE,
        response_payload={"text": "Hello human!"},
        cookies_to_export=[{"name": "session", "value": "xyz"}],
        visited_urls=[],
        submitted_prompts=[],
        restored=[],
    )
    relay = build_relay(tmp_path, session)
    task = OracleTask(prompt="Offer guidance", target=Workspace.ORACLE)
    result = relay.execute(task)
    assert isinstance(result, OracleRelayResult)
    assert session.visited_urls == [TaskRouter().route(task).url]
    assert session.ready_calls == 1
    assert session.submitted_prompts == [task.prompt]
    stored = relay._session_manager.load(Workspace.ORACLE)  # type: ignore[attr-defined]
    assert stored == tuple(session.cookies_to_export)


def test_query_chatgpt_returns_response(tmp_path: Path) -> None:
    session = FakeSession(
        workspace=Workspace.ORACLE,
        response_payload={"text": "The sky is blue."},
        cookies_to_export=[{"name": "session", "value": "chatgpt"}],
        visited_urls=[],
        submitted_prompts=[],
        restored=[],
    )
    relay = build_relay(tmp_path, session)
    task = OracleTask(prompt="What colour is the sky?", target=Workspace.ORACLE)
    result = relay.execute(task)
    assert result.response == "The sky is blue."


def test_codex_query_reports_commit(tmp_path: Path) -> None:
    session = FakeSession(
        workspace=Workspace.CODEX,
        response_payload={"text": "Commit ready", "metadata": {"commit_sha": "abc123"}},
        cookies_to_export=[{"name": "session", "value": "codex"}],
        visited_urls=[],
        submitted_prompts=[],
        restored=[],
    )
    relay = build_relay(tmp_path, session, router=TaskRouter())
    task = OracleTask(prompt="scan repo for TODOs")
    result = relay.execute(task)
    assert result.workspace == Workspace.CODEX
    assert result.metadata["commit_sha"] == "abc123"


def test_timeout_triggers_reauthentication(tmp_path: Path) -> None:
    session = FakeSession(
        workspace=Workspace.ORACLE,
        response_payload={"text": "Recovered"},
        cookies_to_export=[{"name": "session", "value": "new"}],
        visited_urls=[],
        submitted_prompts=[],
        restored=[],
    )

    class FailingScraper(ResponseScraper):
        def __init__(self) -> None:
            super().__init__(timeout=0.01, poll_interval=0.01)
            self.attempts = 0

        def extract(self, session, *, workspace):  # type: ignore[override]
            if self.attempts == 0:
                self.attempts += 1
                raise SessionExpiredError("stale session")
            return super().extract(session, workspace=workspace)

    storage = tmp_path / "cookies.json"
    manager = SessionManager(storage)
    driver = RelayDriver(FakeFactory(session))
    scraper = FailingScraper()

    def reauthenticate(workspace: Workspace, exc: BaseException):
        assert isinstance(exc, SessionExpiredError)
        return [{"name": "session", "value": "refreshed"}]

    handler = ErrorHandler(manager, max_retries=1, reauthenticate=reauthenticate)
    relay = OracleRelay(session_manager=manager, driver=driver, scraper=scraper, error_handler=handler)
    task = OracleTask(prompt="Hello", target=Workspace.ORACLE)
    result = relay.execute(task)
    assert result.response == "Recovered"
    assert manager.load(Workspace.ORACLE) == tuple(session.cookies_to_export)

