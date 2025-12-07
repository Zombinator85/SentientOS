from agents.forms.ssa_disability_agent import SSADisabilityAgent


def test_agent_exposes_selector_maps():
    agent = SSADisabilityAgent(profile={})

    login_page = agent.get_page_structure("login")
    assert login_page["url"] == "https://ssa.gov/disability/login"
    assert login_page["fields"]["password"] == "#password"


def test_agent_resolves_next_pages():
    agent = SSADisabilityAgent(profile={})

    assert agent.next_page("login") == "contact_info"
    assert agent.next_page("work_history") is None
