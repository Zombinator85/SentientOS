from __future__ import annotations

import pytest

from sentientos.agents.browser_automator import BrowserActionError, BrowserAutomator, SocialConfig
from sentientos.metrics import MetricsRegistry


class DummyDriver:
    def __init__(self) -> None:
        self.actions: list[tuple[str, str]] = []

    def open(self, url: str) -> None:
        self.actions.append(("open", url))

    def click(self, selector: str) -> None:
        self.actions.append(("click", selector))

    def type(self, selector: str, text: str) -> None:
        self.actions.append(("type", f"{selector}:{text}"))


def test_browser_automator_budget_and_allowlist() -> None:
    driver = DummyDriver()
    metrics = MetricsRegistry()
    config = SocialConfig(
        enable=True,
        allow_interactive_web=True,
        domains_allowlist=("example.com",),
        daily_action_budget=2,
        require_quorum_for_post=True,
    )
    automator = BrowserAutomator(config, driver_factory=lambda: driver, metrics=metrics)

    automator.open_url("https://example.com/feed")
    automator.click(".like")

    with pytest.raises(BrowserActionError):
        automator.type_text(".compose", "hello")

    status = automator.status()
    assert status["budget_remaining"] == 0
    counters = metrics.snapshot()["counters"]
    assert counters["sos_web_actions_total{kind=open}"] == 1.0
