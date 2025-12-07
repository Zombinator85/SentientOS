import inspect
from typing import Dict

import pytest

from sentientos.self_expansion import SelfExpansionAgent


def test_self_expansion_agent_importable():
    assert SelfExpansionAgent is not None


def test_self_expansion_agent_methods_exist():
    agent = SelfExpansionAgent()
    for method in ("run_self_audit", "propose_upgrades"):
        assert hasattr(agent, method)


def test_self_expansion_agent_signatures():
    audit_sig = inspect.signature(SelfExpansionAgent.run_self_audit)
    assert list(audit_sig.parameters.keys()) == ["self"]
    assert audit_sig.return_annotation == Dict[str, str]

    upgrade_sig = inspect.signature(SelfExpansionAgent.propose_upgrades)
    assert list(upgrade_sig.parameters.keys()) == ["self", "observations"]
    assert upgrade_sig.parameters["observations"].annotation == Dict[str, str]
    assert upgrade_sig.return_annotation is str


def test_self_expansion_agent_placeholders_raise():
    agent = SelfExpansionAgent()
    with pytest.raises(NotImplementedError):
        agent.run_self_audit()

    with pytest.raises(NotImplementedError):
        agent.propose_upgrades({})
