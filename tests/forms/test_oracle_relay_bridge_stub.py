from agents.forms.browser_plan import BrowserPlan, BrowserStep
from agents.forms.oracle_relay_bridge import OracleRelayBridge
from agents.forms.screenshot_plan import ScreenshotPlan, ScreenshotRequest


def test_schedule_screenshot_returns_stub_payload():
    bridge = OracleRelayBridge()
    payload = bridge.schedule_screenshot("login")
    assert payload == {
        "status": "stub_only",
        "page": "login",
        "note": "No real browser execution in Stage-3.",
    }


def test_execute_plan_returns_dry_run_bundle():
    browser_plan = BrowserPlan([BrowserStep(page="login", action_type="fill_username", selector="#u")])
    screenshot_plan = ScreenshotPlan([ScreenshotRequest(page="login")])
    bridge = OracleRelayBridge()

    payload = bridge.execute_plan(browser_plan, screenshot_plan)

    assert payload == {
        "status": "dry_run_execution_stub",
        "browser_steps": [
            {
                "page": "login",
                "action_type": "fill_username",
                "selector": "#u",
                "value": None,
            }
        ],
        "screenshot_requests": [
            {
                "page": "login",
                "type": "screenshot",
            }
        ],
    }
