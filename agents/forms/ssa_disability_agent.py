"""
This module defines deterministic structures for SSA form automation without
any browser automation, network calls, or scheduling behavior. Stage-1 adds
selector map loading and logical routing helpers while keeping interactions
purely structural. Stage-2 introduces dry-run planning of browser actions that
remains entirely inert while preparing for future OracleRelay execution. Stage-
3 adds deterministic screenshot planning hooks without driving a browser.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from agents.forms.browser_plan import BrowserPlan, BrowserStep, build_click_step, build_fill_step
from agents.forms.screenshot_plan import ScreenshotPlan, build_screenshot_request
from agents.forms.schema_validator import validate_profile
from agents.forms.selector_loader import get_page, load_selectors
from agents.forms import page_router
from agents.forms.page_router import PAGE_FLOW
from agents.forms.oracle_session import OracleSession


SCHEMA_PATH = Path(__file__).with_name("schemas").joinpath("ssa_claim_profile.schema.json")


def require_explicit_approval(flag: bool) -> bool:
    """Deterministically gate privileged actions.

    This placeholder will be expanded when PII handling rules are enforced.
    """
    return flag


class SSADisabilityAgent:
    """Bootstrap agent for SSA disability claim preparation."""

    def __init__(self, profile: Dict[str, Any]):
        # Store without mutation to keep profile deterministic
        self.profile = profile
        selectors_path = Path(__file__).with_name("maps").joinpath("ssa_selectors.yaml")
        self.selectors = load_selectors(str(selectors_path))

    def validate(self) -> bool:
        return validate_profile(self.profile, str(SCHEMA_PATH))

    def dry_run(self) -> Dict[str, Any]:
        browser_plan = self.build_dry_run_plan()
        screenshot_plan = self.build_screenshot_plan()
        return {
            "status": "dry_run_plan_ready",
            "browser_plan": browser_plan.as_list(),
            "screenshot_plan": screenshot_plan.as_list(),
            "pages": PAGE_FLOW,
        }

    def get_page_structure(self, page: str) -> Dict[str, Any]:
        return get_page(page, self.selectors)

    def next_page(self, page: str) -> Optional[str]:
        return page_router.next_page(page)

    def build_dry_run_plan(self) -> BrowserPlan:
        steps: list[BrowserStep] = []
        for page in PAGE_FLOW:
            structure = self.get_page_structure(page)
            fields = structure.get("fields", {}) or {}
            actions = structure.get("actions", {}) or {}

            for field_name, selector in fields.items():
                value = self._find_profile_value(field_name)
                if value is not None:
                    steps.append(build_fill_step(page, field_name, selector, value))

            if "next" in actions:
                steps.append(build_click_step(page, "next", actions["next"]))

        return BrowserPlan(steps)

    def build_screenshot_plan(self) -> ScreenshotPlan:
        requests = [build_screenshot_request(page) for page in PAGE_FLOW]
        return ScreenshotPlan(requests)

    def execute(self, relay, approval_flag: bool) -> Dict[str, Any]:
        browser_plan = self.build_dry_run_plan()
        screenshot_plan = self.build_screenshot_plan()
        session = OracleSession(relay, approval_flag)

        if not approval_flag:
            return {"status": "approval_required"}

        execution_log = []

        for page in PAGE_FLOW:
            structure = self.get_page_structure(page)
            url = structure.get("url") if structure else None
            if url:
                nav_result = session.navigate(url)
                execution_log.append({"page": page, "action": "navigate", "result": nav_result})

            fields = structure.get("fields", {}) if structure else {}
            for field_name, selector in (fields or {}).items():
                value = self._find_profile_value(field_name)
                if value is not None:
                    fill_result = session.fill(selector, str(value))
                    execution_log.append(
                        {
                            "page": page,
                            "action": "fill",
                            "field": field_name,
                            "selector": selector,
                            "value": value,
                            "result": fill_result,
                        }
                    )

            actions = structure.get("actions", {}) if structure else {}
            next_selector = (actions or {}).get("next")
            if next_selector:
                click_result = session.click(next_selector)
                execution_log.append(
                    {
                        "page": page,
                        "action": "click",
                        "target": "next",
                        "selector": next_selector,
                        "result": click_result,
                    }
                )

            screenshot_result = session.screenshot()
            execution_log.append({"page": page, "action": "screenshot", "result": screenshot_result})

        return {"status": "execution_complete", "log": execution_log, "pages": PAGE_FLOW}

    def _find_profile_value(self, key: str) -> Optional[Any]:
        def _search(node: Any) -> Optional[Any]:
            if isinstance(node, dict):
                if key in node:
                    return node[key]
                for value in node.values():
                    found = _search(value)
                    if found is not None:
                        return found
            elif isinstance(node, list):
                for item in node:
                    found = _search(item)
                    if found is not None:
                        return found
            return None

        return _search(self.profile)
