from agents.forms.browser_plan import BrowserPlan, BrowserStep, build_click_step, build_fill_step


def test_browser_step_as_dict_returns_expected_mapping():
    step = BrowserStep(page="login", action_type="fill_username", selector="#username", value="ada")
    assert step.as_dict() == {
        "page": "login",
        "action_type": "fill_username",
        "selector": "#username",
        "value": "ada",
    }


def test_browser_plan_as_list_serializes_steps():
    steps = [
        build_fill_step("login", "username", "#username", "ada"),
        build_click_step("contact_info", "next", "button[type=submit]"),
    ]
    plan = BrowserPlan(steps)
    assert plan.as_list() == [step.as_dict() for step in steps]
