from agents.forms.ssa_disability_agent import SSADisabilityAgent


MINIMAL_PROFILE = {
    "auth": {"username": "ada.user", "password": "secret"},
    "contact": {"phone": "555-0100", "email": "ada@example.com"},
    "address": {
        "address_line1": "123 Main St",
        "address_city": "Exampletown",
        "address_state": "CA",
        "address_zip": "90210",
    },
    "conditions": {"primary_condition": "mobility", "secondary_condition": "vision"},
    "work": {"last_worked_date": "2024-01-01", "employer_name": "ACME"},
}


EXPECTED_BROWSER_PLAN = [
    {
        "page": "login",
        "action_type": "fill_username",
        "selector": "#username",
        "value": "ada.user",
    },
    {
        "page": "login",
        "action_type": "fill_password",
        "selector": "#password",
        "value": "secret",
    },
    {
        "page": "contact_info",
        "action_type": "fill_phone",
        "selector": "#contactPhone",
        "value": "555-0100",
    },
    {
        "page": "contact_info",
        "action_type": "fill_email",
        "selector": "#contactEmail",
        "value": "ada@example.com",
    },
    {
        "page": "contact_info",
        "action_type": "fill_address_line1",
        "selector": "#addr1",
        "value": "123 Main St",
    },
    {
        "page": "contact_info",
        "action_type": "fill_address_city",
        "selector": "#city",
        "value": "Exampletown",
    },
    {
        "page": "contact_info",
        "action_type": "fill_address_state",
        "selector": "#state",
        "value": "CA",
    },
    {
        "page": "contact_info",
        "action_type": "fill_address_zip",
        "selector": "#zip",
        "value": "90210",
    },
    {
        "page": "contact_info",
        "action_type": "click_next",
        "selector": "button[type=submit]",
        "value": None,
    },
    {
        "page": "conditions",
        "action_type": "fill_primary_condition",
        "selector": "#primaryCond",
        "value": "mobility",
    },
    {
        "page": "conditions",
        "action_type": "fill_secondary_condition",
        "selector": "#secondaryCond",
        "value": "vision",
    },
    {
        "page": "conditions",
        "action_type": "click_next",
        "selector": "button[type=submit]",
        "value": None,
    },
    {
        "page": "work_history",
        "action_type": "fill_last_worked_date",
        "selector": "#lastWorkedDate",
        "value": "2024-01-01",
    },
    {
        "page": "work_history",
        "action_type": "fill_employer_name",
        "selector": "#employer",
        "value": "ACME",
    },
    {
        "page": "work_history",
        "action_type": "click_next",
        "selector": "button[type=submit]",
        "value": None,
    },
]


EXPECTED_SCREENSHOT_PLAN = [
    {"page": "login", "type": "screenshot"},
    {"page": "contact_info", "type": "screenshot"},
    {"page": "conditions", "type": "screenshot"},
    {"page": "work_history", "type": "screenshot"},
]


def test_dry_run_includes_browser_and_screenshot_plans():
    agent = SSADisabilityAgent(profile=MINIMAL_PROFILE)
    payload = agent.dry_run()

    assert payload["status"] == "dry_run_plan_ready"
    assert payload["browser_plan"] == EXPECTED_BROWSER_PLAN
    assert payload["screenshot_plan"] == EXPECTED_SCREENSHOT_PLAN
    assert payload["pages"] == ["login", "contact_info", "conditions", "work_history"]


def test_build_screenshot_plan_is_deterministic():
    agent = SSADisabilityAgent(profile=MINIMAL_PROFILE)
    screenshot_plan = agent.build_screenshot_plan()

    assert screenshot_plan.as_list() == EXPECTED_SCREENSHOT_PLAN
