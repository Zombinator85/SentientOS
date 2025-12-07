from agents.forms.ssa_disability_agent import SSADisabilityAgent


class RelayStub:
    def __init__(self):
        self.calls = []

    def goto(self, url):
        self.calls.append(("goto", url))
        return {"navigated": url}

    def type(self, selector, value):
        self.calls.append(("type", selector, value))
        return {"typed": selector, "value": value}

    def click(self, selector):
        self.calls.append(("click", selector))
        return {"clicked": selector}

    def screenshot(self):
        self.calls.append(("screenshot", None))
        return b"bytes"


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


def test_execute_requires_explicit_approval():
    relay = RelayStub()
    agent = SSADisabilityAgent(profile=MINIMAL_PROFILE)

    result = agent.execute(relay, approval_flag=False)

    assert result == {"status": "approval_required"}
    assert relay.calls == []


def test_execute_runs_deterministic_sequence():
    relay = RelayStub()
    agent = SSADisabilityAgent(profile=MINIMAL_PROFILE)

    result = agent.execute(relay, approval_flag=True)

    assert result["status"] == "execution_complete"
    assert result["pages"] == ["login", "contact_info", "conditions", "work_history"]
    log = result["log"]

    assert len(log) == 20
    assert log[0]["action"] == "navigate"
    assert log[0]["page"] == "login"
    assert log[0]["result"]["status"] == "navigated"

    fill_actions = [entry for entry in log if entry["action"] == "fill"]
    assert {entry["field"] for entry in fill_actions} == {
        "username",
        "password",
        "phone",
        "email",
        "address_line1",
        "address_city",
        "address_state",
        "address_zip",
        "primary_condition",
        "secondary_condition",
        "last_worked_date",
        "employer_name",
    }

    click_actions = [entry for entry in log if entry["action"] == "click"]
    assert len(click_actions) == 3
    assert all(action["target"] == "next" for action in click_actions)

    screenshot_actions = [entry for entry in log if entry["action"] == "screenshot"]
    assert len(screenshot_actions) == 4
    assert all(action["result"]["status"] == "screenshot" for action in screenshot_actions)

    assert relay.calls == [
        ("goto", "https://ssa.gov/disability/login"),
        ("type", "#username", "ada.user"),
        ("type", "#password", "secret"),
        ("screenshot", None),
        ("type", "#contactPhone", "555-0100"),
        ("type", "#contactEmail", "ada@example.com"),
        ("type", "#addr1", "123 Main St"),
        ("type", "#city", "Exampletown"),
        ("type", "#state", "CA"),
        ("type", "#zip", "90210"),
        ("click", "button[type=submit]"),
        ("screenshot", None),
        ("type", "#primaryCond", "mobility"),
        ("type", "#secondaryCond", "vision"),
        ("click", "button[type=submit]"),
        ("screenshot", None),
        ("type", "#lastWorkedDate", "2024-01-01"),
        ("type", "#employer", "ACME"),
        ("click", "button[type=submit]"),
        ("screenshot", None),
    ]
