"""Stage-3 OracleRelay bridge stub.

Defines deterministic interfaces for future browser automation without
performing any real network or automation work in this stage.
"""
from __future__ import annotations


class OracleRelayBridge:
    """
    Stage-3 stub: defines the interface but performs no browser work.
    """

    def __init__(self):
        pass

    def schedule_screenshot(self, page: str) -> dict:
        return {
            "status": "stub_only",
            "page": page,
            "note": "No real browser execution in Stage-3.",
        }

    def execute_plan(self, browser_plan, screenshot_plan) -> dict:
        """
        Deterministic stub: returns a structured object describing what
        would be executed without touching a browser.
        """
        return {
            "status": "dry_run_execution_stub",
            "browser_steps": browser_plan.as_list(),
            "screenshot_requests": screenshot_plan.as_list(),
        }
