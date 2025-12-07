from agents.forms.screenshot_plan import (
    ScreenshotPlan,
    ScreenshotRequest,
    build_screenshot_request,
)


def test_screenshot_request_as_dict():
    request = ScreenshotRequest(page="login")
    assert request.as_dict() == {"page": "login", "type": "screenshot"}


def test_screenshot_plan_as_list():
    requests = [ScreenshotRequest(page="login"), ScreenshotRequest(page="contact")]
    plan = ScreenshotPlan(requests=requests)
    assert plan.as_list() == [
        {"page": "login", "type": "screenshot"},
        {"page": "contact", "type": "screenshot"},
    ]


def test_build_screenshot_request_order_is_deterministic():
    pages = ["login", "contact", "finish"]
    plan = ScreenshotPlan([build_screenshot_request(page) for page in pages])
    assert plan.as_list() == [
        {"page": "login", "type": "screenshot"},
        {"page": "contact", "type": "screenshot"},
        {"page": "finish", "type": "screenshot"},
    ]
