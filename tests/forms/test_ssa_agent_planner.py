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


EXPECTED_STEPS = [
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


def test_build_dry_run_plan_creates_expected_steps():
    agent = SSADisabilityAgent(profile=MINIMAL_PROFILE)
    plan = agent.build_dry_run_plan()
    assert plan.as_list() == EXPECTED_STEPS


def test_dry_run_returns_structured_plan_bundle():
    agent = SSADisabilityAgent(profile=MINIMAL_PROFILE)
    payload = agent.dry_run()
    assert payload["status"] == "dry_run_plan_ready"
    assert payload["plan"] == EXPECTED_STEPS
    assert payload["pages"] == ["login", "contact_info", "conditions", "work_history"]
