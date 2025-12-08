import pytest

from sentientos.innerworld import InnerWorldOrchestrator
from sentientos.runtime.core_loop import CoreLoop

pytestmark = pytest.mark.no_legacy_skip


def test_federation_digest_surfaces_in_cycle_report():
    loop = CoreLoop()
    cycle = loop.run_cycle({"errors": 0})

    digest = cycle["innerworld"].get("federation_digest")
    consensus = cycle["innerworld"].get("federation_consensus")

    assert isinstance(digest, dict)
    assert "digest" in digest
    assert isinstance(consensus, dict)
    assert "drift_level" in consensus


def test_simulation_mode_skips_federation_layers():
    orchestrator = InnerWorldOrchestrator()

    report = orchestrator.run_cycle({"errors": 0}, simulation=True)

    assert "federation_digest" not in report
    assert "federation_consensus" not in report


def test_federation_layers_are_deterministic():
    loop_a = CoreLoop()
    loop_b = CoreLoop()

    state = {"errors": 1, "plan": {"complexity": 2}}
    digest_a = loop_a.run_cycle(state)["innerworld"].get("federation_digest", {})
    digest_b = loop_b.run_cycle(state)["innerworld"].get("federation_digest", {})

    assert digest_a.get("digest") == digest_b.get("digest")
    assert digest_a.get("components") == digest_b.get("components")


def test_existing_innerworld_outputs_are_preserved():
    loop = CoreLoop()

    result = loop.run_cycle({"progress": 0.5})
    innerworld = result["innerworld"]

    assert "workspace_spotlight" in innerworld
    assert "inner_dialogue" in innerworld
    assert "value_drift" in innerworld
    assert "autobiography" in innerworld
    assert "federation_digest" in innerworld
    assert "federation_consensus" in innerworld
