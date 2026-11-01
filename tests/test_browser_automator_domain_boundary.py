from __future__ import annotations

import pytest

from sentientos.agents.browser_automator import BrowserActionError, BrowserAutomator, SocialConfig


pytestmark = pytest.mark.no_legacy_skip


def _automator() -> BrowserAutomator:
    return BrowserAutomator(
        SocialConfig(
            enable=True,
            domains_allowlist=("example.com",),
            daily_action_budget=3,
        )
    )


def test_actions_use_the_active_allowlisted_page_host() -> None:
    automator = _automator()

    automator.open_url("https://example.com/feed")
    automator.click(".like")
    automator.type_text("#search", "evidence")

    assert automator.status()["budget_remaining"] == 0


def test_allowlist_rejects_a_host_that_only_contains_the_allowed_domain() -> None:
    automator = _automator()

    with pytest.raises(BrowserActionError, match="domain not allowlisted"):
        automator.open_url("https://example.com.attacker.invalid/")

    assert automator.status()["last_action"] is None
