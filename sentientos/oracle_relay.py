"""OracleRelay browser automation subsystem.

This module assembles the browser automation bridge described in the
"5-Pro" blueprint.  The bridge allows SentientOS to re-use authenticated
browser sessions for both the ChatGPT Teams interface ("oracle" guidance)
and the Codex Workspace (GitHub-linked execution environment).  The
implementation focuses on three properties:

* **Isolation** – components are small, dependency injectable and easy to
  substitute in tests where real browsers are not available.
* **Resilience** – the :class:`ErrorHandler` coordinates retries and
  session refreshes when cookies expire, the DOM layout changes or a task
  times out.
* **Observability** – structured results and metadata are returned so that
  higher level orchestrators (for example the :class:`~sentientos.codex_healer.RecoveryLedger`)
  can record what happened.

The primary entry-point is :class:`OracleRelay` which composes the other
classes to fulfil a single automation request.  The driver implementation
defaults to Playwright when available while remaining fully testable with
pure-python fakes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from enum import Enum
from importlib import import_module
import json
from pathlib import Path
import threading
import time
from typing import Any, Protocol, runtime_checkable

from .optional_deps import optional_import

__all__ = [
    "Workspace",
    "OracleTask",
    "TaskRoute",
    "OracleRelayResult",
    "SessionExpiredError",
    "StaleElementError",
    "RelayTimeoutError",
    "SessionManager",
    "BrowserSession",
    "RelayDriver",
    "ResponseScraper",
    "TaskRouter",
    "ErrorHandler",
    "OracleRelay",
    "default_playwright_factory",
]


class Workspace(str, Enum):
    """Enumerated targets supported by the oracle relay."""

    ORACLE = "chatgpt_teams"
    CODEX = "codex_workspace"


DEFAULT_WORKSPACE_URLS: Mapping[Workspace, str] = {
    Workspace.ORACLE: "https://teams.microsoft.com/v2/",  # ChatGPT Teams web UI
    Workspace.CODEX: "https://github.com/login?return_to=/codespaces",  # Codex Workspace landing
}


@dataclass(slots=True, frozen=True)
class OracleTask:
    """High-level request sent to the oracle relay."""

    prompt: str
    attachments: tuple[Path, ...] = ()
    target: Workspace | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class TaskRoute:
    """Routing decision produced by :class:`TaskRouter`."""

    workspace: Workspace
    url: str


@dataclass(slots=True, frozen=True)
class OracleRelayResult:
    """Structured result returned by :class:`OracleRelay`."""

    workspace: Workspace
    prompt: str
    response: str
    metadata: Mapping[str, object]


class SessionExpiredError(RuntimeError):
    """Raised when the browser session no longer has valid authentication."""


class StaleElementError(RuntimeError):
    """Raised when DOM elements become stale during interaction."""


class RelayTimeoutError(TimeoutError):
    """Raised when the relay does not produce a response within the timeout."""


class SessionManager:
    """Persist and recall cookies for ChatGPT Teams and the Codex workspace."""

    def __init__(self, storage_path: Path) -> None:
        self._path = Path(storage_path)
        self._lock = threading.RLock()
        self._cache: MutableMapping[str, list[Mapping[str, Any]]] | None = None

    def load(self, workspace: Workspace) -> tuple[Mapping[str, Any], ...]:
        """Return the cookies previously stored for ``workspace``."""

        with self._lock:
            cache = self._read()
            records = cache.get(workspace.value, [])
            return tuple(dict(record) for record in records)

    def save(self, workspace: Workspace, cookies: Iterable[Mapping[str, Any]]) -> None:
        """Persist ``cookies`` for ``workspace``."""

        with self._lock:
            cache = self._read()
            cache[workspace.value] = [dict(cookie) for cookie in cookies]
            self._write(cache)

    def clear(self, workspace: Workspace) -> None:
        """Drop all cookies stored for ``workspace``."""

        with self._lock:
            cache = self._read()
            if cache.pop(workspace.value, None) is not None:
                self._write(cache)

    def _read(self) -> MutableMapping[str, list[Mapping[str, Any]]]:
        if self._cache is not None:
            return self._cache
        if not self._path.exists():
            self._cache = {}
            return self._cache
        try:
            data = json.loads(self._path.read_text())
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        normalised: MutableMapping[str, list[Mapping[str, Any]]] = {}
        for key, value in data.items():
            if not isinstance(value, list):
                continue
            entries: list[Mapping[str, Any]] = []
            for item in value:
                if isinstance(item, Mapping):
                    entries.append(dict(item))
            normalised[str(key)] = entries
        self._cache = normalised
        return self._cache

    def _write(self, cache: MutableMapping[str, list[Mapping[str, Any]]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(cache, indent=2, sort_keys=True))
        self._cache = cache


@runtime_checkable
class BrowserSession(Protocol):
    """Interface implemented by browser automation sessions."""

    def restore_cookies(self, cookies: Sequence[Mapping[str, Any]]) -> None:
        ...

    def export_cookies(self) -> Sequence[Mapping[str, Any]]:
        ...

    def goto(self, url: str) -> None:
        ...

    def ensure_ready(self) -> None:
        ...

    def submit(self, prompt: str, attachments: Sequence[Path] = ()) -> None:
        ...

    def wait_for_response(self, *, timeout: float | None = None) -> Mapping[str, Any] | str:
        ...


class RelayDriver:
    """Thin wrapper that orchestrates the browser session lifecycle."""

    def __init__(
        self,
        factory: Callable[[Workspace], AbstractContextManager[BrowserSession]],
    ) -> None:
        self._factory = factory

    def transmit(
        self,
        route: TaskRoute,
        prompt: str,
        *,
        attachments: Sequence[Path] = (),
        cookies: Sequence[Mapping[str, Any]] = (),
        scraper: "ResponseScraper",
    ) -> tuple[str, Mapping[str, Any], Sequence[Mapping[str, Any]]]:
        """Execute ``prompt`` against the routed workspace."""

        with self._factory(route.workspace) as session:
            if cookies:
                session.restore_cookies(list(cookies))
            session.goto(route.url)
            session.ensure_ready()
            session.submit(prompt, attachments=attachments)
            response, metadata = scraper.extract(session, workspace=route.workspace)
            new_cookies = session.export_cookies()
        return response, metadata, new_cookies


class ResponseScraper:
    """Collect text responses rendered in the browser DOM."""

    def __init__(self, *, timeout: float = 60.0, poll_interval: float = 0.5) -> None:
        self._timeout = timeout
        self._poll_interval = poll_interval

    def extract(self, session: BrowserSession, *, workspace: Workspace) -> tuple[str, Mapping[str, Any]]:
        """Return the response text and metadata from ``session``."""

        deadline = None if self._timeout is None else time.monotonic() + self._timeout
        while True:
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            if deadline is not None and remaining <= 0:
                raise RelayTimeoutError(f"Timed out waiting for {workspace.value} response")
            payload = session.wait_for_response(timeout=remaining)
            text: str
            metadata: Mapping[str, Any]
            if isinstance(payload, str):
                text = payload
                metadata = {}
            elif isinstance(payload, Mapping):
                text = str(payload.get("text", "")).strip()
                meta = payload.get("metadata", {})
                metadata = meta if isinstance(meta, Mapping) else {}
            else:
                text = str(payload)
                metadata = {}
            if text:
                return text, metadata
            time.sleep(self._poll_interval)


class TaskRouter:
    """Determine which workspace should process a prompt."""

    ORACLE_KEYWORDS = {
        "advice",
        "idea",
        "plan",
        "next step",
        "what should",
    }
    CODEX_KEYWORDS = {
        "commit",
        "repo",
        "patch",
        "diff",
        "pull request",
        "scan",
        "fix",
    }

    def __init__(self, *, urls: Mapping[Workspace, str] | None = None) -> None:
        self._urls = dict(DEFAULT_WORKSPACE_URLS)
        if urls:
            self._urls.update(urls)

    def route(self, task: OracleTask) -> TaskRoute:
        """Return the :class:`TaskRoute` to satisfy ``task``."""

        workspace = task.target or self._infer_workspace(task.prompt)
        url = self._urls.get(workspace, DEFAULT_WORKSPACE_URLS[workspace])
        return TaskRoute(workspace=workspace, url=url)

    def _infer_workspace(self, prompt: str) -> Workspace:
        lowered = prompt.lower()
        if any(keyword in lowered for keyword in self.CODEX_KEYWORDS):
            return Workspace.CODEX
        if any(keyword in lowered for keyword in self.ORACLE_KEYWORDS):
            return Workspace.ORACLE
        # Fallback: assume general advice goes to GPT-5
        return Workspace.ORACLE


class ErrorHandler:
    """Retry automation tasks when common failure modes occur."""

    def __init__(
        self,
        session_manager: SessionManager,
        *,
        max_retries: int = 1,
        reauthenticate: Callable[[Workspace, BaseException], Sequence[Mapping[str, Any]]] | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._max_retries = max_retries
        self._reauthenticate = reauthenticate

    def run(
        self,
        workspace: Workspace,
        operation: Callable[[], OracleRelayResult],
    ) -> OracleRelayResult:
        """Execute ``operation`` with retry semantics."""

        attempt = 0
        while True:
            try:
                return operation()
            except (RelayTimeoutError, SessionExpiredError, StaleElementError) as exc:
                if attempt >= self._max_retries:
                    raise
                attempt += 1
                self._session_manager.clear(workspace)
                if self._reauthenticate is not None:
                    cookies = self._reauthenticate(workspace, exc)
                    if cookies:
                        self._session_manager.save(workspace, cookies)


class OracleRelay:
    """Coordinate routing, browser driving and scraping."""

    def __init__(
        self,
        *,
        session_manager: SessionManager,
        driver: RelayDriver,
        scraper: ResponseScraper,
        router: TaskRouter | None = None,
        error_handler: ErrorHandler | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._driver = driver
        self._scraper = scraper
        self._router = router or TaskRouter()
        self._error_handler = error_handler or ErrorHandler(session_manager)

    def execute(self, task: OracleTask) -> OracleRelayResult:
        """Process ``task`` and return the automation result."""

        route = self._router.route(task)

        def _operation() -> OracleRelayResult:
            cookies = self._session_manager.load(route.workspace)
            response, metadata, new_cookies = self._driver.transmit(
                route,
                task.prompt,
                attachments=task.attachments,
                cookies=cookies,
                scraper=self._scraper,
            )
            self._session_manager.save(route.workspace, new_cookies)
            return OracleRelayResult(
                workspace=route.workspace,
                prompt=task.prompt,
                response=response,
                metadata=dict(metadata),
            )

        return self._error_handler.run(route.workspace, _operation)


# ---------------------------------------------------------------------------
# Optional Playwright automation


class _PlaywrightSession(AbstractContextManager["_PlaywrightSession"], BrowserSession):
    """Best-effort Playwright session used when Playwright is installed."""

    def __init__(self, workspace: Workspace, *, headless: bool = True) -> None:
        self._workspace = workspace
        self._headless = headless
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self) -> "_PlaywrightSession":
        if optional_import("playwright", feature="oracle_playwright") is None:
            raise RuntimeError("Playwright is not installed")
        sync_playwright = import_module("playwright.sync_api").sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - requires playwright
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    # BrowserSession implementation -------------------------------------------------

    def restore_cookies(self, cookies: Sequence[Mapping[str, Any]]) -> None:  # pragma: no cover - optional
        if self._context is None:
            return
        if cookies:
            self._context.add_cookies(list(cookies))

    def export_cookies(self) -> Sequence[Mapping[str, Any]]:  # pragma: no cover - optional
        if self._context is None:
            return ()
        return list(self._context.cookies())

    def goto(self, url: str) -> None:  # pragma: no cover - optional
        if self._page is None:
            raise RuntimeError("Page not initialised")
        self._page.goto(url, wait_until="networkidle")

    def ensure_ready(self) -> None:  # pragma: no cover - optional
        if self._page is None:
            raise RuntimeError("Page not initialised")
        self._page.wait_for_timeout(1000)

    def submit(self, prompt: str, attachments: Sequence[Path] = ()) -> None:  # pragma: no cover - optional
        if self._page is None:
            raise RuntimeError("Page not initialised")
        textbox = self._page.wait_for_selector("textarea, div[role='textbox']")
        textbox.click()
        textbox.fill(prompt)
        textbox.press("Enter")

    def wait_for_response(self, *, timeout: float | None = None) -> Mapping[str, Any] | str:  # pragma: no cover
        if self._page is None:
            raise RuntimeError("Page not initialised")
        millis = None if timeout is None else timeout * 1000
        locator = self._page.wait_for_selector("div[data-message-author]", timeout=millis)
        return {"text": locator.inner_text()}


def default_playwright_factory(*, headless: bool = True) -> Callable[[Workspace], AbstractContextManager[BrowserSession]]:
    """Return a factory that produces Playwright-backed sessions."""

    def _factory(workspace: Workspace) -> AbstractContextManager[BrowserSession]:
        return _PlaywrightSession(workspace, headless=headless)

    return _factory
