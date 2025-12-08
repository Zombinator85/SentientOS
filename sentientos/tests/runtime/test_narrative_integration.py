import copy

import pytest

from sentientos.runtime import CoreLoop

pytestmark = pytest.mark.no_legacy_skip


def test_narrative_exposed_in_cycle_output():
    loop = CoreLoop()
    output = loop.run_cycle({"progress": 0.1, "errors": 0})

    assert "narrative_chapters" in output
    assert "identity_summary" in output
    assert output["narrative_chapters"]
    assert output["identity_summary"]["chapter_count"] == len(output["narrative_chapters"])


def test_narrative_updates_only_on_real_cycles():
    loop = CoreLoop()
    loop.run_cycle({"progress": 0.2})
    chapters_after_real_cycle = loop.innerworld.get_narrative_chapters()

    loop.innerworld.run_simulation({"plan": {"action": "simulate"}})
    chapters_after_simulation = loop.innerworld.get_narrative_chapters()

    assert chapters_after_simulation == chapters_after_real_cycle


def test_narrative_outputs_are_deterministic():
    state = {"errors": 1, "progress": 0.3}

    loop_a = CoreLoop()
    loop_b = CoreLoop()

    output_a = copy.deepcopy(loop_a.run_cycle(state))
    output_b = copy.deepcopy(loop_b.run_cycle(state))

    assert output_a["identity_summary"] == output_b["identity_summary"]
    assert output_a["narrative_chapters"] == output_b["narrative_chapters"]
