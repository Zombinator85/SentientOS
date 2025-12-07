from agents.forms.schema_validator import validate_profile
from agents.forms.ssa_disability_agent import SCHEMA_PATH


def test_validate_profile_with_valid_data():
    profile = {
        "claimant": {"name": {"first": "Ada", "last": "Lovelace"}, "ssn_last4": "1234", "dob": "1815-12-10"},
        "contact": {"phone": "555-1234", "email": "ada@example.com"},
        "address": {"line1": "1 Analytical St", "city": "London", "state": "UK", "zip": "N1"},
        "conditions": {"primary": ["compute"], "secondary": ["math"]},
        "work": {"last_worked_date": "1843-09-01"},
        "medical": {"providers": ["Royal Society"]},
        "benefits_context": {"programs": ["SSD"]},
        "consents": {"ssa_827_release": True},
    }

    assert validate_profile(profile, str(SCHEMA_PATH)) is True


def test_validate_profile_with_malformed_data():
    profile = {
        "claimant": {"name": {"first": "Ada", "last": 42}},
        "consents": {"ssa_827_release": "yes"},
    }

    assert validate_profile(profile, str(SCHEMA_PATH)) is False
