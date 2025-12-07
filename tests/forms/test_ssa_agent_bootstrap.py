from agents.forms.ssa_disability_agent import SSADisabilityAgent, require_explicit_approval, SCHEMA_PATH


def test_dry_run_returns_expected_structure():
    agent = SSADisabilityAgent(profile={})
    assert agent.dry_run() == {"status": "dry_run_ready", "profile_loaded": True}


def test_validation_passes_for_matching_schema():
    agent = SSADisabilityAgent(
        profile={
            "claimant": {"name": {"first": "Ada", "last": "Lovelace"}},
            "consents": {"ssa_827_release": True},
        }
    )
    assert agent.validate() is True


def test_require_explicit_approval_is_deterministic():
    assert require_explicit_approval(False) is False
    assert require_explicit_approval(True) is True
