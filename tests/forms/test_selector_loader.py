from pathlib import Path

from agents.forms.selector_loader import get_page, load_selectors


SELECTOR_PATH = Path(__file__).resolve().parents[2] / "agents" / "forms" / "maps" / "ssa_selectors.yaml"


def test_load_selectors_returns_expected_structure():
    selectors = load_selectors(str(SELECTOR_PATH))

    assert "login" in selectors
    assert selectors["login"]["fields"]["username"] == "#username"
    assert selectors["work_history"]["actions"]["next"] == "button[type=submit]"


def test_get_page_handles_missing_page_deterministically():
    selectors = load_selectors(str(SELECTOR_PATH))

    assert get_page("contact_info", selectors)["fields"]["phone"] == "#contactPhone"
    assert get_page("missing", selectors) == {}
