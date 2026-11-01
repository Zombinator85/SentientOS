from __future__ import annotations

from sentientos.agents.browser_automator import BrowserAutomator, SocialConfig
from sentientos.autonomy.audit import AutonomyActionLogger


def test_browser_audit_keeps_dynamic_detail_fields(tmp_path) -> None:
    logger = AutonomyActionLogger(path=tmp_path / "actions.jsonl")
    automator = BrowserAutomator(
        SocialConfig(enable=True, allow_interactive_web=True, domains_allowlist=("example.test",)),
        audit_logger=logger,
    )

    automator._log("open", "performed", target="https://example.test", reason="test")

    entry = logger.recent()[0]
    assert entry["target"] == "https://example.test"
    assert entry["reason"] == "test"
